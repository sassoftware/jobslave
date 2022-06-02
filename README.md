# SAS App Engine Jobslave -- Archived Repository
**Notice: This repository is part of a Conary/rpath project at SAS that is no longer supported or maintained. Hence, the repository is being archived and will live in a read-only state moving forward. Issues, pull requests, and changes will no longer be accepted.**

Overview
--------
The jobslave is a tool used to construct a wide variety of system image types
from a Conary appliance group. It transforms a job description emitted by
*mint* in the form of a JSON blob into an image of the chosen type and
configuration.  The environment in which it runs is constructed and managed by
the *jobmaster*. Tasks may include partitioning and formatting a disk image,
installing contents, performing post-install adjustments, installing a
bootloader, transforming the disk image into a format specific to the desired
virtualization type, and archiving image files into a tarball or ZIP. The
resulting image files as well as ongoing progress updates are uploaded back to
mint by way of the jobmaster's API proxy.

The partitioning and formatting code is also used by *catalog-service* to
assist in deploying images to Amazon EC2 elastic block storage.
