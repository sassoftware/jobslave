#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#


all: default-all

install: default-install
	install -D -m0644 config $(DESTDIR)$(jsdir)/config
	install -D -m0755 jobslave.init $(DESTDIR)$(initdir)/jobslave.init

clean: default-clean


raw2vmdk: raw2vmdk.c
	$(CC) $(CFLAGS) -lm -lz $< -o $@


include ../Make.rules
include ../Make.defs
