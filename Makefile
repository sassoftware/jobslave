#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

SUBDIRS = bin jobslave


all: default-all

install: default-install
	mkdir -p $(DESTDIR)$(jsdata)
	cp -r templates skel pixmaps $(DESTDIR)$(jsdata)/

clean: default-clean


include Make.rules
include Make.defs
