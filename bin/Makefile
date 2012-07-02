#
# Copyright (c) rPath, Inc.
#

bin_files = jobslave

bin_progs = raw2vmdk


all: default-all

install: default-install

clean: default-clean


raw2vmdk: raw2vmdk.c
	$(CC) $(CFLAGS) -Wall -lm -lz $< -o $@

CFLAGS ?= -O2 -g -D_FORTIFY_SOURCE=2 -fstack-protector


include ../Make.rules
include ../Make.defs
