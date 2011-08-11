#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved.
#

bin_files = jobslave

bin_progs = raw2vmdk


all: default-all

install: default-install

clean: default-clean


raw2vmdk: raw2vmdk.c
	$(CC) $(CFLAGS) -Wall -lm -lz $< -o $@


include ../Make.rules
include ../Make.defs
