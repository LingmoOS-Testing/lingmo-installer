CLEANFILES = 

AM_CPPFLAGS = $(MOCK_RESOLVER_CFLAGS)
AM_LDFLAGS = $(MOCK_RESOLVER_LIBS)

lib_LTLIBRARIES = libubimockresolver.la

libubimockresolver_la_SOURCES = mockresolver.h mockresolver.c
libubimockresolver_la_LDFLAGS = -version-info 0:0:0 -no-undefined \
	-export-symbols-regex "^[^_].*"
libubimockresolver_la_LIBADD = $(MOCK_RESOLVER_LIBS)
if HAVE_INTROSPECTION
-include $(INTROSPECTION_MAKEFILE)
INTROSPECTION_SCANNER_ARGS = --add-include-path=$(srcdir)
INTROSPECTION_COMPILER_ARGS = --includedir=$(srcdir)

INTROSPECTION_GIRS = Lingmo-installerMockResolver-1.0.gir

introspection_sources = $(libubimockresolver_la_SOURCES)

Lingmo-installerMockResolver-1.0.gir: libubimockresolver.la
Lingmo-installerMockResolver_1_0_gir_INCLUDES = Gio-2.0
Lingmo-installerMockResolver_1_0_gir_SCANNERFLAGS = --identifier-prefix=Lingmo-installer
Lingmo-installerMockResolver_1_0_gir_LIBS = libubimockresolver.la
Lingmo-installerMockResolver_1_0_gir_FILES = $(introspection_sources)

girdir = $(datadir)/gir-1.0
gir_DATA = $(INTROSPECTION_GIRS)

typelibdir = $(libdir)/girepository-1.0
typelib_DATA = $(INTROSPECTION_GIRS:.gir=.typelib)

CLEANFILES += $(gir_DATA) $(typelib_DATA)
endif
