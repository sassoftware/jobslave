#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

SUBDIRS = bin jobslave dist


all: default-all

install: default-install
	mkdir -p $(DESTDIR)$(jsdir)
	cp -r templates skel pixmaps $(DESTDIR)$(jsdir)/

clean: default-clean


include Make.rules
include Make.defs
