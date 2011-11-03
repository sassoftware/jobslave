/* Copyright (c) 2010 rPath, Inc.
 * All rights reserved.
 */

#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64

#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <errno.h>
#include <libgen.h>
#include <zlib.h>
#include <assert.h>

#if defined(__i386__) || defined(__x86_64__)
# define breakpoint do {__asm__ __volatile__ ("int $03");} while (0)
#endif

/* Program version */
#define VER                 "0.1"

#define CID_NOPARENT        0x0
#define SPARSE_MAGICNUMBER  0x564d444b /* 'V' 'M' 'D' 'K' */
#define VERSION             0x3
#define FLAGS               0x3        /* flags for monolithicSparse */
#define SOFLAGS             0x30001    /* flags for streamOptimized */
#define SELC                '\n'
#define NELC                ' '
#define DELC1               '\r'
#define DELC2               '\n'
#define GRAINSIZE           0x00010000 /*bytes in a grain*/
#define GRAINSECTORS        0x00000080 /*sectors in a grain*/
#define COMPRESSION_NONE    0          /* no compression (for monolithicSparse) */
#define COMPRESSION_DEFLATE 1          /* compression algorithm for streamOptimized */
// #define GD_AT_END           0xffffffff    /* signify that grain dir is at the end */

/* 512 Grain Tables Entries Per Grain Table */
#define GTEPERGT            0x00000200
#define SECTORSIZE          0x00000200 /* 512 Bytes per sector */

/* Conversion macros */
#define BYTES(x)    ((x)<<9)
#define SECTORS(x)    ((x)>>9)

/* define two vmdk disk types */
#define MONOLITHIC_SPARSE 0
#define STREAM_OPTIMIZED  1
#define VMDKTYPE(x)  (x==MONOLITHIC_SPARSE ? "monolithicSparse" : "streamOptimized" )

/* Marker types for streamOptimized vmdk */
#define MARKER_EOS    0
#define MARKER_GT     1
#define MARKER_GD     2
#define MARKER_FOOTER 3

/* define GTE/GDE entry size as a constant */
#define OFFSETSIZE  sizeof(u_int32_t)

u_int8_t zerograin[GRAINSIZE];

typedef u_int64_t  SectorType;
typedef u_int8_t   Bool;

int zeropad(off_t numbytes, FILE * file);

#pragma pack(1)

typedef struct Marker {
     SectorType val;
     u_int32_t     size;
     union {
        u_int32_t  type;
        u_int8_t   data[0];
     } u;
} Marker;

typedef struct GrainMarker {
     SectorType lba;
     u_int32_t     size;
     // sizeof() is more useful when the data is left out
} GrainMarker;

typedef struct EOSMarker {
     SectorType val;
     u_int32_t     size;
     u_int32_t     type;
     u_int8_t      pad[496];
} EOSMarker;

typedef struct MetaDataMarker {
     /* Number of sectors occupied by the metadata, excluding the marker itself */
     SectorType numSectors;
     u_int32_t     size;        /* 0 */
     u_int32_t     type;        /* GT, GD, or FOOTER */
     u_int8_t      pad[496];    /* pad with zeroes */
     // sizeof() is more useful when the metadata is left out
} MetaDataMarker;

typedef struct SparseExtentHeader {
    u_int32_t   magicNumber;        /* VMDK */
    u_int32_t   version;            /* 1 */
    u_int32_t   flags;              /* 3 */
    SectorType  capacity;           /* Size of the extent */
    SectorType  grainSize;          /* 128 */
    SectorType  descriptorOffset;   /* 1 */
    SectorType  descriptorSize;     /* 20, can this be smaller? */
    u_int32_t   numGTEsPerGT;       /* 512 */
    SectorType  rgdOffset;          /* 21 */
    SectorType  gdOffset;           /* depends on how many GTEs per GT and
                                     * the total size of the extent
                                     */
    SectorType  overHead;           /* 256 or so */
    Bool        uncleanShutdown;    /* False */
    char        singleEndLineChar;  /* SELC */
    char        nonEndLineChar;     /* NELC */
    char        doubleEndLineChar1; /* DELC1 */
    char        doubleEndLineChar2; /* DELC2 */
    u_int16_t   compressAlgorithm;
    u_int8_t    pad[433];
} SparseExtentHeader;

int verbose = 0;
int vmdkType = MONOLITHIC_SPARSE;

#define VPRINT  if(verbose) printf

int numGTs(off_t outsize) {
    int numgrains = ceil((double)outsize / GRAINSIZE);
    return ceil((double)numgrains / GTEPERGT);
}

int GT0Offset(off_t numgts) {
    return ceil((double)(numgts * 4) / SECTORSIZE);
}

void SparseExtentHeader_init(SparseExtentHeader *hd, off_t outsize) {
    memset(hd, 0, sizeof(SparseExtentHeader));
    size_t numgts = numGTs(outsize);
    size_t gt0offset = GT0Offset(numgts);
    hd->magicNumber =       SPARSE_MAGICNUMBER;
    hd->version =           VERSION;
    hd->flags =             (vmdkType == MONOLITHIC_SPARSE ? FLAGS : SOFLAGS );
    hd->capacity =          SECTORS(outsize);
    hd->grainSize =         SECTORS(GRAINSIZE);
    hd->descriptorOffset =  1;
    hd->descriptorSize   =  20;
    hd->numGTEsPerGT =      GTEPERGT;
    hd->rgdOffset =         (vmdkType == MONOLITHIC_SPARSE ? hd->descriptorSize + hd->descriptorOffset : 0);

    /*offset of the first GT + total number of GTs * 4 sectors per GT */
    u_int32_t metadatasize =      gt0offset + numgts * 4;
    if (vmdkType == MONOLITHIC_SPARSE) {
        hd->gdOffset  =     hd->rgdOffset + metadatasize;
    } else {
        hd->gdOffset  =     (u_int64_t) -1;
    }

    /* The overHead is grain aligned */
    if (vmdkType == MONOLITHIC_SPARSE) {
        hd->overHead = ceil((hd->gdOffset + metadatasize) / (float) hd->grainSize) * hd->grainSize;
    } else {
        hd->overHead = GRAINSECTORS;
    }
    hd->uncleanShutdown =   0;
    hd->singleEndLineChar = SELC;
    hd->nonEndLineChar =    NELC;
    hd->doubleEndLineChar1= DELC1;
    hd->doubleEndLineChar2= DELC2;
    hd->compressAlgorithm = (u_int16_t) (vmdkType == MONOLITHIC_SPARSE ? COMPRESSION_NONE : COMPRESSION_DEFLATE );
}

size_t _fwrite(const void *ptr, size_t size, size_t nmemb, FILE *stream) {
    /* call fwrite and bail on errors */
    if (fwrite(ptr, size, nmemb, stream) != nmemb) {
       VPRINT("Write failed. Exiting");
       exit(1);
    } else {
       return (size * nmemb);
    }
}

int writeDescriptorFile(FILE * of, const off_t outsize,
                        const char * outfile,
                        const u_int32_t cylinders,
                        const u_int8_t heads,
                        const u_int8_t sectors,
                        const char * adapter) {
    size_t len = strlen(outfile);
    char * cpoutfile = (char*)malloc(sizeof(char)*(len + 1));
    const char *extentType;
    strncpy(cpoutfile, outfile, strlen(outfile));
    cpoutfile[len] = '\0';
    int returner = 0;

    if (vmdkType == MONOLITHIC_SPARSE) {
        extentType = "RW";
    } else {
        extentType = "RO";
    }

    returner += fprintf(of,
            "# Disk DescriptorFile\n"
            "version=1\n"
            "CID=fffffffe\n"
            "parentCID=ffffffff\n"
            "createType=\"%s\"\n"
            "\n"
            "# Extent description\n"
            "%s %lld SPARSE \"%s\"\n",
            VMDKTYPE(vmdkType), extentType,
            (long long)SECTORS(outsize), basename(cpoutfile));

    returner += fprintf(of, "\n"
        "# The Disk Data Base \n"
        "#DDB\n\n"
        "ddb.adapterType = \"%s\"\n"
        "ddb.geometry.sectors = \"%d\"\n"
        "ddb.geometry.heads = \"%d\"\n"
        "ddb.geometry.cylinders = \"%d\"\n"
        "ddb.toolsVersion = \"8193\"\n"
        "ddb.virtualHWVersion = \"7\"\n", adapter, sectors, heads, cylinders);

    free(cpoutfile);
    return returner;
}

int writeCompressedGrainDirectory(u_int32_t numGTs, u_int32_t * gd, FILE * of) {
    off_t bytesWritten;
    MetaDataMarker gdm;
    memset(&gdm, 0, sizeof(MetaDataMarker));
    gdm.numSectors = 1;  /* this needs to be determined by number of GTs */
    gdm.type       = MARKER_GD;
    bytesWritten = _fwrite((void *)&gdm, sizeof(MetaDataMarker), 1, of);

    VPRINT("Writing Grain Directory\n");
    bytesWritten += _fwrite((void *) gd, sizeof(u_int32_t), numGTs, of);
    /* pad to a sector boundary */
    off_t padding = SECTORSIZE - bytesWritten % SECTORSIZE;
    if (padding != SECTORSIZE) {
        bytesWritten += zeropad(padding, of);
    } 
    return bytesWritten;
}

int writeCompressedGrainTable(u_int32_t * gt, FILE * of) {
    int bytesWritten;
    MetaDataMarker gtm;
    memset(&gtm, 0, sizeof(MetaDataMarker));
    gtm.numSectors = SECTORS(GTEPERGT * sizeof(u_int32_t));
    gtm.type       = MARKER_GT;
    bytesWritten = _fwrite((void *)&gtm, sizeof(MetaDataMarker), 1, of);

    VPRINT("Writing Grain Table\n");
    bytesWritten += _fwrite((void *) gt, sizeof(u_int32_t), GTEPERGT, of);
    return bytesWritten;
}

int writeCompressedGrain(FILE * infile, SectorType lba, FILE * of) {
    z_stream strm;
    int ret;
    int compressedBytes = 0;
    off_t bytesWritten = 0;
    u_int8_t buf[GRAINSIZE];
    u_int8_t outbuf[2*GRAINSIZE];
    memset(buf, 0, GRAINSIZE*sizeof(u_int8_t));
    memset(outbuf, 0, GRAINSIZE*sizeof(u_int8_t));

    fread((void *)&buf, GRAINSIZE*sizeof(u_int8_t), 1, infile);
    if (! memcmp(&buf, &zerograin, GRAINSIZE*sizeof(u_int8_t))) {
        VPRINT("grain at LBA %lld is zero. skipping.\n", (long long)lba);
        return 0;
    }

    /* allocate deflate state */
    strm.zalloc = Z_NULL;
    strm.zfree = Z_NULL;
    strm.opaque = Z_NULL;
    ret = deflateInit(&strm, Z_DEFAULT_COMPRESSION);
    if (ret != Z_OK)
        exit(2);

    strm.avail_in = GRAINSIZE;
    strm.next_in = buf;
    strm.next_out = outbuf;
    strm.avail_out = 2*GRAINSIZE;
    ret = deflate(&strm, Z_FINISH);    /* no bad return value */
    assert(ret != Z_STREAM_ERROR);  /* state not clobbered */
    compressedBytes = 2*GRAINSIZE - strm.avail_out;
    assert(strm.avail_in == 0);     /* all input will be used */
    assert(ret == Z_STREAM_END);        /* stream will be complete */

    /* clean up and return */
    (void)deflateEnd(&strm);

    /* write grain marker */
    GrainMarker gm;
    memset(&gm, 0, sizeof(GrainMarker));
    gm.lba = lba;
    gm.size = compressedBytes;
    bytesWritten = _fwrite((void *)&gm, sizeof(GrainMarker), 1, of);
    bytesWritten += _fwrite((void *)&outbuf, sizeof(u_int8_t), compressedBytes, of);
    VPRINT("Wrote a compressed grain of %lld bytes\n", (long long)bytesWritten);
    off_t padding = bytesWritten % SECTORSIZE;
    if (padding) {
        bytesWritten += zeropad(SECTORSIZE - padding, of);
    }
    return bytesWritten; 
}

void writeFooter(SparseExtentHeader * hd, FILE * of) {
    /* The footer is nearly identical to the header. */
    MetaDataMarker fm;
    memset(&fm, 0, sizeof(MetaDataMarker));
    fm.numSectors = 1;
    fm.type       = MARKER_FOOTER;
    _fwrite((void *)&fm, sizeof(MetaDataMarker), 1, of);
    
    VPRINT("Writing the footer\n");
    _fwrite((void*)hd, sizeof(SparseExtentHeader), 1, of);
    return;
}

void writeEndOfStream(FILE * of) {
    EOSMarker eos;
    VPRINT("Writing End-of-stream marker\n");
    memset(&eos, 0, sizeof(EOSMarker));
    _fwrite((void *)&eos, sizeof(eos), 1, of);
    return;
}

int writeGrainDirectory(const size_t offset, const off_t outsize, FILE * of) {
    size_t returner = 0;
    size_t i;
    size_t stop = numGTs(outsize);
    size_t start = offset + GT0Offset(stop);
    u_int32_t cur;
    for (i=0; i < stop; i++) {
        /* The next GT pointed to by a GDE is 4 sectors away  */
        cur = start + (i * 4);
        returner += fwrite((void*)&cur, sizeof(cur), 1, of);
    }
    return returner * sizeof(cur);
}

int writeGrainTables(const size_t offset, const off_t outsize, FILE * of) {
    size_t returner = 0;
    size_t i, numGrains = (outsize / GRAINSIZE) + ((outsize % GRAINSIZE) ? 1 : 0);
    size_t grainSize = SECTORS(GRAINSIZE);
    u_int32_t cur;
    for (i = 0; i < numGrains; i++) {
        /* The next Grain is SECTORS(GRAINSIZE) away */
        cur = offset + (i * grainSize);
        returner += fwrite((void*)&cur, sizeof(cur), 1, of);
    }
    return returner * sizeof(cur);
}

int writeGrainTableData(const SparseExtentHeader * header, u_int32_t * grainTable, const size_t numgte, FILE * fd)
{
    size_t numgts = numGTs(BYTES(header->capacity));
    size_t gt0offset = GT0Offset(numgts);
    int returner = 0;
    //Seek to the first offset, and dump
    fseek(fd, BYTES(header->rgdOffset + gt0offset), SEEK_SET);
    returner += fwrite((void*)grainTable, sizeof(u_int32_t), numgte, fd);

    fseek(fd, BYTES(header->gdOffset + gt0offset), SEEK_SET);
    returner += fwrite((void*)grainTable, sizeof(u_int32_t), numgte, fd);
    return returner;
}

off_t copyData(const char* infile, const off_t outsize,
             const SparseExtentHeader * header, FILE * of) {
    FILE *in;
    if (strcmp(infile, "-") != 0) {
        in = fopen(infile, "rb");
        if (in == NULL) {
            perror("failed to open input");
            return -1;
        }
    } else {
        in = stdin;
    }

    /* Always have 512 entries per grain table */
    u_int32_t limit = numGTs(outsize) * 512;
    u_int32_t * grainTable = (u_int32_t*)malloc(limit * sizeof(u_int32_t));
    memset((void*)grainTable, 0, limit * sizeof(u_int32_t));
    off_t returner = 0;
    u_int32_t currentSector = header->overHead;
    u_int32_t pos = 0;
    u_int64_t zero = 0L;
    u_int8_t buf[GRAINSIZE];
    size_t read;
    u_int32_t numGrains = (outsize / GRAINSIZE) + ((outsize % GRAINSIZE) ? 1 : 0);
    u_int32_t curGrain = 0;
    while((read = fread((void*)&buf, sizeof(u_int8_t), GRAINSIZE, in))) {
        VPRINT("Copying grain %d of %d", ++curGrain, numGrains);
        /* Check to make sure it's not all zeros */
        int i, rem, stop;
        Bool blank = 1;
        rem = read % sizeof(u_int64_t);
        stop = read - rem;
        for(i=0; i < stop; i+=sizeof(u_int64_t))
        {
            //Check one u_int64_t at a time
            //memcmp
            if (memcmp(&buf[i], &zero, sizeof(u_int64_t))) {
                blank = 0;
                break;
            }
        }
        if(blank && rem){
            if(memcmp(&buf[i], &zero, rem)) {
                blank = 0;
            }
        }

        /* Pad the file to be grain aligned (RBL-3487) */
        if (read < GRAINSIZE) {
            VPRINT("\nPadding end of file to align to grain by %lld bytes.",
                    (long long)(GRAINSIZE-read));
            for (i=read; i<GRAINSIZE; i+=sizeof(u_int64_t))
                buf[i] = zero;
            read = GRAINSIZE;
        }

        //Finally, if it's not blank, write it, and add an entry in the grainTable
        if(!blank) {
            grainTable[pos] = currentSector;
            currentSector += GRAINSECTORS;
            returner += fwrite((void*)&buf, sizeof(u_int8_t), read, of);
            VPRINT(" written\n");
        }
        else {
            VPRINT(" skipped\n");
        }
        pos++;
    }
    fclose(in);
    /* Write the grainTable to the two offsets */
    writeGrainTableData(header, grainTable, limit, of);
    free(grainTable);
    VPRINT("wrote %lld bytes\n", (long long)returner);
    return returner * sizeof(u_int8_t);
}


static void usage(char * name)
{
    printf("%s - Version %s\n", name, VER);
    printf("%s -C cylinders [-H heads] [-S sectors] [-A adapter] [-l size] [ -s ] "
	    "infile.img outfile.vmdk\n\n"
            "-C  Number of cylinders in infile.img\n"
            "-H  Number of heads in infile.img\n"
            "-S  Number of sectors in infile.img\n"
            "-A  Adapter: legal values are ide, lsilogic or buslogic\n"
            "-l  Size of the input image (optional if input is a file)\n"
            "-s  Use streamOptimized format rather than monolithicSparse\n"
            "infile.img    RAW disk image, or - for standard input\n"
            "outfile.vmdk  VMware virtual disk\n\n",
            name);
}

int zeropad(off_t numbytes, FILE * file)
{
    off_t i;
    for( i = 0; i < numbytes; i++) {
        fputc(0, file);
    }
    return i;
}

int main(int argc, char ** argv) {
    SparseExtentHeader header;
    int c;
    long long fileSize = -1;
    u_int8_t heads = 0x10, sectors = 0x3f;
    u_int32_t cylinders = 0x0;
    char adapter[256];
    memset(adapter, 0, 256);
    strncpy(adapter, "ide", 3);

    memset(zerograin, 0, GRAINSIZE);

    // Parse command line options
    do {
        c = getopt(argc, argv, "C:H:S:A:l:vs");
        switch (c) {
            case 'C': cylinders = atoi(optarg); break;
            case 'H': heads = atoi(optarg); break;
            case 'S': sectors = atoi(optarg); break;
            case 'v': verbose = 1; break;
            case 'A': strncpy(adapter, optarg, 255); break;
            case 'l': fileSize = atoll(optarg); break;
            case 's': vmdkType = STREAM_OPTIMIZED; break;
        }
    } while (c >= 0);

    if (cylinders == 0 || (argc - optind != 2)) {
        usage(argv[0]);
        return -1;
    }
    if (strcmp(adapter, "ide") && \
          strcmp(adapter, "lsilogic") && \
          strcmp(adapter, "buslogic")) {
        usage(argv[0]);
        return -1;
    }
    char * infile = argv[optind];
    VPRINT("Reading from %s\n", infile);
    char * outfile = argv[optind+1];
    VPRINT("Writing to %s\n", outfile);

    if (fileSize == -1) {
        /* Figure out how big the extent needs to be. */
        struct stat istat;
        if (strcmp(infile, "-") == 0) {
            fprintf(stderr, "error: -l is required when using standard input\n");
            return 1;
        }
        if (stat(infile, &istat)) {
            perror("error reading input");
            return 1;
        }
        fileSize = istat.st_size;
    }
    VPRINT("Source file is %llu bytes\n", fileSize);
    off_t padding = SECTORSIZE - (fileSize % SECTORSIZE);
    off_t outsize = fileSize + (padding == SECTORSIZE ? 0: padding);
    VPRINT("Padding %llu bytes\n", (unsigned long long)(outsize - fileSize));
    VPRINT("Total size of the destination image: %llu\n",
            (unsigned long long)outsize);
    size_t numgts = numGTs(outsize);

    VPRINT("Creating the sparse extent header\n");
    SparseExtentHeader_init(&header, outsize);

    FILE * of = fopen(outfile, "wb");
    if(of) {
        // Write the header
        VPRINT("Writing the header\n");
        fwrite((void*)&header, sizeof(SparseExtentHeader), 1, of);
        // Write the descriptor
        VPRINT("Padding to the first sector\n");
        zeropad(BYTES(header.descriptorSize) - writeDescriptorFile(of, outsize, outfile, cylinders, heads, sectors, adapter), of);
        if (vmdkType == MONOLITHIC_SPARSE) {
            // Write the rGDE
            VPRINT("Writing the redundant Grain Directory\n");
            size_t sizeofGDE = GT0Offset(numGTs(outsize));
            zeropad( BYTES(sizeofGDE) - writeGrainDirectory(header.rgdOffset, outsize, of), of);
            // Write the rGTs
            VPRINT("Writing the redundant Grain Tables\n");
            zeropad( BYTES(numGTs(outsize) * 4) - writeGrainTables(header.overHead, outsize, of), of);
            // Write the GDE
            VPRINT("Writing the Grain Directory\n");
            zeropad( BYTES(sizeofGDE) - writeGrainDirectory(header.gdOffset, outsize, of), of);
            // Write the GTs
            VPRINT("Writing the Grain Tables\n");
            zeropad( BYTES(numGTs(outsize) * 4) - writeGrainTables(header.overHead, outsize, of), of);
            // Align to grain
            off_t pos;
            pos = ftello(of);
            padding = GRAINSIZE - (pos % GRAINSIZE);
            zeropad((padding == GRAINSIZE ? 0: padding), of);
            // Write the grains
            VPRINT("Copying the data\n");
            if (copyData(infile, outsize, &header, of) < 0) {
                return 1;
            }
        } else {
            FILE *in;
            if (strcmp(infile, "-") != 0) {
                in = fopen(infile, "rb");
                if (in == NULL) {
                    perror("failed to open input");
                    return 1;
                }
            } else {
                in = stdin;
            }
            // Write grains in loops
            VPRINT("Padding to 64k\n");
            off_t pos = ftello(of);
            SectorType lba = 0;
            zeropad(GRAINSIZE - pos, of);
            u_int32_t gd[numgts];
            memset(gd, 0, numgts*sizeof(u_int32_t));
            u_int32_t gt[GTEPERGT];
            pos = GRAINSIZE;
            int gtNum;
            for (gtNum=0; lba <= SECTORS(outsize); gtNum++) {
                int grain;
                int cgsize;
                memset(gt, 0, GTEPERGT*sizeof(u_int32_t));
                for (grain=0; (grain < GTEPERGT) && (lba <= SECTORS(outsize)); ) {
                    cgsize = writeCompressedGrain(in, lba, of);
                    if (cgsize) {
                        gt[grain++] = SECTORS(pos);
                        pos += cgsize;
                    }
                    lba += GRAINSECTORS;
                }
                if (grain != 0) {
                    gd[gtNum] = SECTORS(pos+sizeof(MetaDataMarker));
                    pos += writeCompressedGrainTable(gt, of);
                }
            }
            pos = ftello(of);
            header.gdOffset = SECTORS(pos) + 1;
            writeCompressedGrainDirectory(gtNum, gd, of);
            writeFooter(&header, of);
            writeEndOfStream(of);
        }
    }
    if(of)
        fclose(of);
    VPRINT("Finished\n");
    return 0;
}

/* vim: set sts=4 sw=4 expandtab : */
