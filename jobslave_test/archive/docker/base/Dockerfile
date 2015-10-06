FROM centos

MAINTAINER Walter

RUN [ "/bin/bash", "-c", "for i in c e; do for j in parent child; do ln -sf /usr/bin/echo /usr/bin/$i$j; done; done" ]
