#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


from conary.deps import deps

stockFlavors = {
    "1#x86":
        "~MySQL-python.threadsafe, ~X, ~!alternatives, ~!bootstrap,"
        "~!builddocs, ~buildtests, ~desktop, ~dietlibc, ~emacs, ~gcj,"
        "~glibc.tls, ~gnome, ~!grub.static, ~gtk, ~ipv6, ~kde, ~!xen, ~!domU, ~!dom0,"
        "~!kernel.debug, ~!kernel.debugdata, ~!kernel.numa, ~krb, ~ldap,"
        "~nptl, ~!openssh.smartcard, ~!openssh.static_libcrypto, ~pam, ~!kernel.pae,"
        "~pcre, ~perl, ~!pie, ~!postfix.mysql, ~python, ~qt, ~readline,"
        "~sasl, ~!selinux, ~sqlite.threadsafe, ~ssl, ~tcl, ~tcpwrappers,"
        "~tk, ~!xorg-x11.xprint is: x86(~cmov, ~i486, ~i586, ~i686, ~mmx,"
        "~sse2)",

    "1#x86_64":
        "~MySQL-python.threadsafe, ~X, ~!alternatives, ~!bootstrap,"
        "~!builddocs, ~buildtests,desktop, ~!dietlibc, ~emacs, ~gcj,"
        "~glibc.tls, ~gnome, ~grub.static, ~gtk, ~ipv6, ~kde, ~!kernel.debug,"
        "~!kernel.debugdata, ~!kernel.numa, ~krb, ~ldap, ~nptl, ~!xen, ~!domU, ~!dom0,"
        "~!openssh.smartcard,~!openssh.static_libcrypto, ~pam, ~pcre,"
        "~perl, ~!pie, ~!postfix.mysql, ~python, ~qt, ~readline, ~sasl,"
        "~!selinux, ~sqlite.threadsafe, ~ssl, ~tcl, ~tcpwrappers, ~tk,"
        "~!xorg-x11.xprint is: x86(~i486,~i586,~i686,~sse2) x86_64",
}

stockFlavorPaths = {
   "1#x86_64":
        ["~X, ~!alternatives, !bootstrap, ~builddocs,"
         "~buildtests, ~desktop, ~!dietlibc, ~emacs, ~gcj,"
         "~gnome, ~gtk, ~ipv6, ~kde, ~krb, ~ldap, ~nptl,"
         "pam, ~pcre, ~perl, ~!pie, ~python, ~qt, ~!xen, ~!domU, ~!dom0,"
         "~readline, ~!sasl, ~!selinux, ssl, ~tcl,"
         "tcpwrappers, ~tk, ~!xen, ~!xfce is: x86_64(~nx)",
         "~X, ~!alternatives, !bootstrap, ~builddocs,"
         "~buildtests, ~desktop, ~!dietlibc, ~emacs, ~gcj,"
         "~gnome, ~gtk, ~ipv6, ~kde, ~krb, ~ldap, ~nptl,"
         "pam, ~pcre, ~perl, ~!pie, ~python, ~qt,"
         "~readline, ~!sasl, ~!selinux, ssl, ~tcl,"
         "tcpwrappers, ~tk, ~!xen, ~!xfce is: x86(~cmov,"
         "~i486, ~i586, ~i686, ~mmx, ~nx, ~sse, ~sse2) "
         "x86_64(~nx)"],
    "1#x86":
        ["~MySQL-python.threadsafe, ~X, ~!alternatives, ~!bootstrap,"
        "~!builddocs, ~buildtests, ~desktop, ~dietlibc, ~emacs, ~gcj,"
        "~glibc.tls, ~gnome, ~!grub.static, ~gtk, ~ipv6, ~kde, ~!xen, ~!domU, ~!dom0,"
        "~!kernel.debug, ~!kernel.debugdata, ~!kernel.numa, ~krb, ~ldap,"
        "~nptl, ~!openssh.smartcard, ~!openssh.static_libcrypto, ~pam,"
        "~pcre, ~perl, ~!pie, ~!postfix.mysql, ~python, ~qt, ~readline,"
        "~sasl, ~!selinux, ~sqlite.threadsafe, ~ssl, ~tcl, ~tcpwrappers,"
        "~tk, ~!xorg-x11.xprint is: x86(~cmov, ~i486, ~i586, ~i686, ~mmx,"
        "~sse2)"],
}

# Set up a flavor search path we have to search x86_64 first, because
# the x86 flavor also satisfies x86, but not the other way around.
# As we add flavors to the lists above, we will need to extend the
# pathSearchOrder, but hopefully we won't have too many more order-dependent
# searches.
pathSearchOrder = ['1#x86_64', '1#x86']

def getStockFlavor(inFlavor):
    for x in pathSearchOrder:
        if inFlavor.satisfies(deps.ThawFlavor(x)):
            return deps.parseFlavor(stockFlavors[x])

def getStockFlavorPath(inFlavor):
    for x in pathSearchOrder:
        if inFlavor.satisfies(deps.ThawFlavor(x)):
            return [deps.parseFlavor(y) for y in stockFlavorPaths[x]]
