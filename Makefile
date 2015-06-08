#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved.
#
 
SUBDIRS = bin jobslave


all: default-all

install: default-install
	mkdir -p $(DESTDIR)$(jsdata)
	cp -r templates skel pixmaps $(DESTDIR)$(jsdata)/
	
	mkdir -p $(DESTDIR)$(templatemount)
	touch $(DESTDIR)$(templatemount)/.keep

clean: default-clean


include Make.rules
include Make.defs
