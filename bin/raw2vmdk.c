/* Copyright (c) 2010 rPath, Inc.
 * All rights reserved.
 */

#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64

#include <sys/types.h>
#include <sys/stat.h>
#include <alloca.h>
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
#define VER                 "0.2"

#define CID_NOPARENT        0x0
#define SPARSE_MAGICNUMBER  0x564d444b /* 'V' 'M' 'D' 'K' */
/* http://www.vmware.com/support/developer/vddk/vmdk_50_technote.pdf
 * There is no mention of version 3 (according to RBL-4831, it is required for
 * streamOptimized)
 * For monolithic, version 2 is not required, since we're not creating a
 * sparse file proper.
 * */
#define VERSION             0x1
#define SOVERSION           0x3
#define FLAGS               0x3        /* flags for monolithicSparse */
#define SOFLAGS             0x30001    /* flags for streamOptimized */
#define SELC                '\n'
#define NELC                ' '
#define DELC1               '\r'
#define DELC2               '\n'
#define GRAINSECTORS        0x00000080 /*sectors in a grain*/
#define COMPRESSION_NONE    0          /* no compression (for monolithicSparse) */
#define COMPRESSION_DEFLATE 1          /* compression algorithm for streamOptimized */
#define GD_AT_END           0xffffffffffffffff /* signify that grain dir is at the end */

/* 512 Grain Tables Entries Per Grain Table */
#define GTEPERGT            0x00000200
#define SECTORSIZE          0x00000200 /* 512 Bytes per sector */
#define GRAINSIZE           ( GRAINSECTORS * SECTORSIZE ) /*bytes in a grain*/

/* Conversion macros */
#define BYTES(x)    ((x)<<9)
#define SECTORS(x)    ((x)>>9)
#define PAD(x, y) ((x) % (y) == 0 ? (x) : (x) + (y) - (x) % (y))
#define MAX(x, y) ((x) > (y) ? (x) : (y))

/* define two vmdk disk types */
#define MONOLITHIC_SPARSE 2
#define STREAM_OPTIMIZED  1
#define TWO_GB_MAX_EXTENT_SPARSE 6 /* bitwise 2 + 4  */
#define VMDKTYPE(x) (x == MONOLITHIC_SPARSE ? "monolithicSparse" : (x == STREAM_OPTIMIZED ? "streamOptimized" : "twoGbMaxExtentSparse"))

/* Marker types for streamOptimized vmdk */
#define MARKER_EOS    0
#define MARKER_GT     1
#define MARKER_GD     2
#define MARKER_FOOTER 3

/* define GTE/GDE entry size as a constant */
#define OFFSETSIZE  sizeof(u_int32_t)

#define MAX_EXTENT_SIZE_MB ((off_t)2047) /* Megabytes */
#define MAX_EXTENT_SIZE_BYTES (MAX_EXTENT_SIZE_MB * 1024 * 1024) /* bytes */
#define MAX_MONOLITHIC_SIZE ((off_t)4095 * 1024 * 1024)
#define VMDKFILETMPL "-s%03d"

u_int8_t zerograin[GRAINSIZE];
u_int32_t zerogt[GTEPERGT];

typedef u_int64_t  SectorType;
typedef u_int8_t   Bool;

off_t zeropad(off_t numbytes, FILE * file);

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

int gdSize(int numgts) {
    /*
     * We need a multiple of GRAINSECTORS (128)
     * */
    return GRAINSECTORS * ceil((double)numgts / GRAINSECTORS);
}

void SparseExtentHeader_init(SparseExtentHeader *hd, off_t outsize, SectorType descriptorSize) {
    memset(hd, 0, sizeof(SparseExtentHeader));
    size_t numgts = numGTs(outsize);
    size_t gt0offset = GT0Offset(numgts);
    hd->magicNumber =       SPARSE_MAGICNUMBER;
    hd->version =           (vmdkType == STREAM_OPTIMIZED ? SOVERSION : VERSION);
    hd->flags =             (vmdkType == STREAM_OPTIMIZED ? SOFLAGS : FLAGS );
    hd->capacity =          SECTORS(outsize);
    hd->grainSize =         SECTORS(GRAINSIZE);
    hd->descriptorOffset =  (descriptorSize == 0 ? 0 : 1);
    hd->descriptorSize   =  descriptorSize;
    hd->numGTEsPerGT =      GTEPERGT;
    // We need to leave at least one sector free for the header, hence the MAX
    hd->rgdOffset =         (vmdkType == STREAM_OPTIMIZED ? 0 : MAX(hd->descriptorSize + hd->descriptorOffset, 1));

    /*offset of the GD + total number of GTs * 4 sectors per GT */
    u_int32_t metadatasize =      gt0offset + numgts * 4;
    if (vmdkType == STREAM_OPTIMIZED) {
        hd->gdOffset  =     GD_AT_END;
    } else {
        hd->gdOffset  =     hd->rgdOffset + metadatasize;
    }

    /* The overHead is grain aligned */
    if (vmdkType == STREAM_OPTIMIZED) {
        hd->overHead = GRAINSECTORS;
    } else {
        hd->overHead = PAD(hd->gdOffset + metadatasize, hd->grainSize);
    }
    hd->uncleanShutdown =   0;
    hd->singleEndLineChar = SELC;
    hd->nonEndLineChar =    NELC;
    hd->doubleEndLineChar1= DELC1;
    hd->doubleEndLineChar2= DELC2;
    hd->compressAlgorithm = (u_int16_t) (vmdkType == STREAM_OPTIMIZED ? COMPRESSION_DEFLATE : COMPRESSION_NONE);
}

size_t _fwrite(const void *ptr, size_t size, size_t nmemb, FILE *stream) {
    /* call fwrite and bail on errors */
    if (fwrite(ptr, size, nmemb, stream) != nmemb) {
       VPRINT("Write failed. Exiting\n");
       exit(1);
    } else {
       return (size * nmemb);
    }
}

SectorType writeDescriptorFile(FILE * of, const off_t * outsizes,
                        char ** outfiles,
                        u_int16_t outfilesCount,
                        const u_int32_t cylinders,
                        const u_int8_t heads,
                        const u_int8_t sectors,
                        const char * adapter) {
    int i;
    const char * extentType;
    SectorType returner = 0;

    if (vmdkType == STREAM_OPTIMIZED) {
        extentType = "RDONLY";
    } else {
        extentType = "RW";
    }

    returner += fprintf(of,
            "# Disk DescriptorFile\n"
            "version=1 \n"
            "CID=fffffffe \n"
            "parentCID=ffffffff \n"
            "createType=\"%s\" \n"
            "\n"
            "# Extent description\n",
            VMDKTYPE(vmdkType));
    for (i = 0; i < outfilesCount; i++) {
        /* Need to copy the string, just because of basename */
        char * cpout = strdup(outfiles[i]);
        returner += fprintf(of,
            "%s %lld SPARSE \"%s\"\n",
            extentType,
            (long long)SECTORS(outsizes[i]), basename(cpout));
        free(cpout);
    }

    returner += fprintf(of, "\n"
        "# The Disk Data Base \n"
        "#DDB\n\n"
        "ddb.adapterType = \"%s\"\n"
        "ddb.encoding = \"UTF-8\"\n"
        "ddb.geometry.cylinders = \"%d\"\n"
        "ddb.geometry.heads = \"%d\"\n"
        "ddb.geometry.sectors = \"%d\"\n"
        "ddb.toolsVersion = \"8193\"\n"
        "ddb.virtualHWVersion = \"7\"\n", adapter, cylinders, heads, sectors);

    return returner;
}

int writeCompressedGrainDirectory(u_int32_t * gd, int gdsize, FILE * of) {
    off_t bytesWritten;
    MetaDataMarker gdm;
    memset(&gdm, 0, sizeof(MetaDataMarker));
    gdm.numSectors = gdsize / GRAINSECTORS;  /* this needs to be determined by number of GTs */
    gdm.type       = MARKER_GD;
    bytesWritten = _fwrite((void *)&gdm, sizeof(MetaDataMarker), 1, of);

    VPRINT("Writing Grain Directory\n");
    bytesWritten += _fwrite((void *) gd, sizeof(u_int32_t), gdsize, of);
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
    size_t bytesRead = 0;
    u_int8_t buf[GRAINSIZE];
    u_int8_t outbuf[2*GRAINSIZE];
    memset(buf, 0, GRAINSIZE*sizeof(u_int8_t));
    memset(outbuf, 0, GRAINSIZE*sizeof(u_int8_t));

    bytesRead = fread(buf, 1, GRAINSIZE*sizeof(u_int8_t), infile);
    if (bytesRead == 0) {
        VPRINT("End of file reached.\n");
        return 0;
    }

    if (! memcmp(buf, zerograin, GRAINSIZE*sizeof(u_int8_t))) {
        VPRINT("grain at LBA %lld is zero. skipping.\n", (long long)lba);
        return 0;
    }

    /* allocate deflate state */
    strm.zalloc = Z_NULL;
    strm.zfree = Z_NULL;
    strm.opaque = Z_NULL;
    ret = deflateInit(&strm, 1);
    if (ret != Z_OK)
        exit(2);

    strm.avail_in = bytesRead;
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

int writeGrainTableData(const SparseExtentHeader * header, u_int32_t * grainTable, const size_t numgte, FILE * fd)
{
    size_t numgts = numGTs(BYTES(header->capacity));
    size_t gt0offset = GT0Offset(numgts);
    int returner = 0;
    VPRINT("Writing redundant grain tables\n");
    fseek(fd, BYTES(header->rgdOffset + gt0offset), SEEK_SET);
    returner += fwrite((void*)grainTable, sizeof(u_int32_t), numgte, fd);

    VPRINT("Writing grain tables\n");
    fseek(fd, BYTES(header->gdOffset + gt0offset), SEEK_SET);
    returner += fwrite((void*)grainTable, sizeof(u_int32_t), numgte, fd);
    return returner;
}

Bool isZeroBlock(const u_int8_t buf[], size_t count)
{
    u_int64_t zero = 0L;
    int i, rem, stop;
    rem = count % sizeof(u_int64_t);
    stop = count - rem;
    for(i=0; i < stop; i+=sizeof(u_int64_t)) {
        //Check one u_int64_t at a time
        //memcmp
        if (memcmp(&buf[i], &zero, sizeof(u_int64_t)))
            return 0;
    }
    if (rem) {
        if(memcmp(&buf[i], &zero, rem)) {
            return 0;
        }
    }
    return 1;
}

off_t copyData(FILE *in, const off_t outsize,
             const SparseExtentHeader * header, FILE * of) {
    /* Always have 512 entries per grain table */
    u_int32_t limit = numGTs(outsize) * 512;
    u_int32_t * grainTable = (u_int32_t*)malloc(limit * sizeof(u_int32_t));
    memset((void*)grainTable, 0, limit * sizeof(u_int32_t));
    off_t returner = 0;
    u_int32_t currentSector = header->overHead;
    u_int32_t pos = 0;
    u_int8_t buf[GRAINSIZE];
    size_t read;
    u_int32_t numGrains = PAD(outsize, GRAINSIZE) / GRAINSIZE;
    u_int32_t curGrain;
    for (curGrain = 0; curGrain < numGrains; curGrain++) {
        VPRINT("Copying grain %d of %d", curGrain + 1, numGrains);
        read = fread(buf, sizeof(u_int8_t), GRAINSIZE, in);
        if (!read) {
            fprintf(stderr, "\nShort read on grain %u\n", curGrain);
            break;
        }
        Bool blank = isZeroBlock(buf, read);
        /* Pad the file to be grain aligned (RBL-3487) */
        if (read < GRAINSIZE) {
            VPRINT("\nPadding end of file to align to grain by %lld bytes.",
                    (long long)(GRAINSIZE-read));
            memset(buf + read, '\0', GRAINSIZE - read);
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

off_t zeropad(off_t numbytes, FILE * file)
{
    if (numbytes <= 0)
        return 0;
    if (numbytes > 1)
        fseek(file, numbytes - 1, SEEK_CUR);
    fputc(0, file);
    return numbytes;
}

char * vmdkFileTemplate(const char *outfile)
{
    /* Return a template for naming multiple files.
     * file.ext -> file-s%03d.ext
     * file-with-no-ext -> file-with-no-ext-s%03d */
    int outfileLen = strlen(outfile);
    char *template = (char *)malloc(outfileLen + 7);
    char *ptr;
    template = strncpy(template, outfile, outfileLen);
    ptr = strrchr(template, '.');
    if (ptr == NULL) {
        /* No extension; just append -s%03d */
        strcat(template, VMDKFILETMPL);
        return template;
    }
    const char *ext = outfile + (ptr - template);
    strcpy(ptr, VMDKFILETMPL);
    ptr += strlen(VMDKFILETMPL);
    strcpy(ptr, ext);
    return template;
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
    memset(zerogt, 0, GTEPERGT * sizeof(u_int32_t));

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
    off_t outsize = PAD(fileSize, SECTORSIZE);
    VPRINT("Padding %llu bytes\n", (unsigned long long)(outsize - fileSize));
    size_t numgts = numGTs(outsize);

    FILE *inf;
    if (strcmp(infile, "-") == 0)
        inf = stdin;
    else {
        inf = fopen(infile, "rb");
        if (!inf) {
            perror("error reading input");
            return 4;
        }
    }

    char ** outfiles;
    off_t * outsizes;
    u_int16_t outfilesCount, fileNo;
    if (vmdkType != STREAM_OPTIMIZED && outsize > MAX_MONOLITHIC_SIZE) {
        vmdkType = TWO_GB_MAX_EXTENT_SPARSE;
        int i;
        off_t sizeLeft = outsize;
        const char * template = vmdkFileTemplate(outfile);
        int templateLen = strlen(template);
        outfilesCount = PAD(outsize, MAX_EXTENT_SIZE_BYTES) / MAX_EXTENT_SIZE_BYTES;
        outfiles = (char **)alloca(outfilesCount * sizeof(char *));
        outsizes = (off_t *)alloca(outfilesCount * sizeof(off_t));
        for (i = 0; i < outfilesCount; i++) {
            outsizes[i] = sizeLeft > MAX_EXTENT_SIZE_BYTES ? MAX_EXTENT_SIZE_BYTES : sizeLeft;
            sizeLeft -= MAX_EXTENT_SIZE_BYTES;
            outfiles[i] = (char *)alloca(templateLen + 1);
            sprintf(outfiles[i], template, i+1);
        }
    } else {
        outsizes = (off_t *)alloca(sizeof(off_t));
        outsizes[0] = outsize;
        outfiles = (char **)alloca(sizeof(char*));
        outfiles[0] = outfile;
        outfilesCount = 1;
    }

    for (fileNo = 0; fileNo < outfilesCount; fileNo++) {
        VPRINT("File %d/%d: %lld bytes: %s\n", fileNo + 1, outfilesCount,
                (unsigned long long)outsizes[fileNo], outfiles[fileNo]);
    }

    FILE *devnull = fopen("/dev/null", "wb");
    if (!devnull) {
        fprintf(stderr, "Error opening %s: %s\n", "/dev/null",
                strerror(errno));
        return 2;
    }

    if (vmdkType == TWO_GB_MAX_EXTENT_SPARSE) {
        /* The main vmdk file only contains the descriptor */
        FILE * of = fopen(outfile, "wb");
        if (!of) {
            fprintf(stderr, "Error opening %s: %s\n", outfile,
                    strerror(errno));
            return 3;
        }
        writeDescriptorFile(of, outsizes, outfiles, outfilesCount,
            cylinders, heads, sectors, adapter);
        fclose(of);
    }

    for (fileNo = 0; fileNo < outfilesCount; fileNo++) {
        VPRINT("Creating the sparse extent header for %s (%d/%d)\n",
                outfiles[fileNo], fileNo+1, outfilesCount);
        FILE * of = fopen(outfiles[fileNo], "wb");
        if (!of) {
            fprintf(stderr, "Error opening %s: %s\n", outfiles[fileNo],
                    strerror(errno));
            continue;
        }
        SectorType descriptorSize = 0;
        if (vmdkType != TWO_GB_MAX_EXTENT_SPARSE) {
            // We've written the descriptor in the case of 2gbmax
            // Write descriptor file, to compute its length (it is cheap)
            assert(outfilesCount == 1);
            descriptorSize = writeDescriptorFile(devnull, outsizes, outfiles,
                    outfilesCount, cylinders, heads, sectors, adapter);
            descriptorSize = SECTORS(PAD(descriptorSize, SECTORSIZE));
        }
        SparseExtentHeader_init(&header, outsizes[fileNo], descriptorSize);

        // Write the header
        VPRINT("Writing the header\n");
        _fwrite((void*)&header, sizeof(SparseExtentHeader), 1, of);

        if (descriptorSize) {
            // Write the descriptor
            VPRINT("Padding to the first sector\n");
            zeropad(BYTES(header.descriptorSize) -
                    writeDescriptorFile(of, outsizes, outfiles, outfilesCount,
                        cylinders, heads, sectors, adapter), of);
        }
        if (vmdkType != STREAM_OPTIMIZED) {
            // Write the rGDE
            VPRINT("Writing the redundant Grain Directory\n");
            // Skip to the rgd position first, this will zero-pad
            fseek(of, BYTES(header.rgdOffset), SEEK_SET);
            writeGrainDirectory(header.rgdOffset, outsizes[fileNo], of);

            VPRINT("Writing the Grain Directory\n");
            fseek(of, BYTES(header.gdOffset), SEEK_SET);
            writeGrainDirectory(header.gdOffset, outsizes[fileNo], of);

            // Align to grain; write a zero byte just to make sure we have at
            // least overHead bytes in the image (corner case for a
            // zero-filled file)
            fseek(of, BYTES(header.overHead)-1, SEEK_SET);
            fputc('\0', of);

            // Write the grains. This also writes the grain tables
            VPRINT("Copying the data\n");
            if (copyData(inf, outsizes[fileNo], &header, of) < 0) {
                return 1;
            }
        } else {
            // Write grains in loops
            VPRINT("Padding to 64k\n");
            off_t pos = ftello(of);
            SectorType lba = 0;
            zeropad(GRAINSIZE - pos, of);

            int gdsize = gdSize(numgts);
            u_int32_t *gd = (u_int32_t *)alloca(sizeof(u_int32_t) * gdsize);
            memset(gd, 0, gdsize * sizeof(u_int32_t));
            u_int32_t gt[GTEPERGT];
            pos = GRAINSIZE;
            int gtNum;
            for (gtNum=0; lba <= SECTORS(outsize); gtNum++) {
                int grain;
                int cgsize;
                memset(gt, 0, GTEPERGT*sizeof(u_int32_t));
                for (grain=0; (grain < GTEPERGT) && (lba <= SECTORS(outsize)); grain++) {
                    /* writeCompressedGrain reads GRAINSIZE bytes */
                    cgsize = writeCompressedGrain(inf, lba, of);
                    if (cgsize) {
                        gt[grain] = SECTORS(pos);
                        pos += cgsize;
                    }
                    lba += GRAINSECTORS;
                }
                if (grain != 0 && memcmp(gt, zerogt, GTEPERGT*sizeof(u_int32_t))) {
                    gd[gtNum] = SECTORS(pos+sizeof(MetaDataMarker));
                    pos += writeCompressedGrainTable(gt, of);
                }
            }
            pos = ftello(of);
            header.gdOffset = SECTORS(pos) + 1;
            writeCompressedGrainDirectory(gd, gdsize, of);
            writeFooter(&header, of);
            writeEndOfStream(of);
        }
        VPRINT("Closing %s\n", outfiles[fileNo]);
        fclose(of);
    }
    fclose(devnull);
    fclose(inf);
    VPRINT("Finished\n");
    return 0;
}

/* vim: set sts=4 sw=4 expandtab : */
