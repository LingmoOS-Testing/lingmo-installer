/* MockResolver - a very stupid resolver used in test code
 *
 * This resolver always resolves a given hostname successfully, and returns
 * an error for anything else.  It only implements just enough of the API to
 * fool the usersetup plugin.
 *
 * Copyright (C) 2012 Canonical Ltd.
 * Author: Colin Watson <cjwatson@lingmo.com>
 *
 * This file is part of Lingmo-installer.
 *
 * Lingmo-installer is free software; you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free
 * Software Foundation; either version 2 of the License, or at your option)
 * any later version.
 *
 * Lingmo-installer is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with Lingmo-installer; if not, write to the Free Software Foundation, Inc., 51
 * Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
 */

#ifndef _LINGMO-INSTALLER_MOCK_RESOLVER_H
#define _LINGMO-INSTALLER_MOCK_RESOLVER_H

#include <glib.h>
#include <glib-object.h>
#include <gio/gio.h>

G_BEGIN_DECLS

#define LINGMO-INSTALLER_TYPE_MOCK_RESOLVER lingmo-installer_mock_resolver_get_type()

#define LINGMO-INSTALLER_MOCK_RESOLVER(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST ((obj), \
  LINGMO-INSTALLER_TYPE_MOCK_RESOLVER, Lingmo-installerMockResolver))

#define LINGMO-INSTALLER_MOCK_RESOLVER_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST ((klass), \
  LINGMO-INSTALLER_TYPE_MOCK_RESOLVER, Lingmo-installerMockResolverClass))

#define LINGMO-INSTALLER_IS_MOCK_RESOLVER(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE ((obj), \
  LINGMO-INSTALLER_TYPE_MOCK_RESOLVER))

#define LINGMO-INSTALLER_IS_MOCK_RESOLVER_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE ((klass), \
  LINGMO-INSTALLER_TYPE_MOCK_RESOLVER))

#define LINGMO-INSTALLER_MOCK_RESOLVER_GET_CLASS(obj) \
  (G_TYPE_INSTANCE_GET_CLASS ((obj), \
  LINGMO-INSTALLER_TYPE_MOCK_RESOLVER, Lingmo-installerMockResolverClass))

typedef struct _Lingmo-installerMockResolver Lingmo-installerMockResolver;
typedef struct _Lingmo-installerMockResolverClass Lingmo-installerMockResolverClass;
typedef struct _Lingmo-installerMockResolverPrivate Lingmo-installerMockResolverPrivate;

struct _Lingmo-installerMockResolver
{
  GResolver parent;

  Lingmo-installerMockResolverPrivate *priv;
};

struct _Lingmo-installerMockResolverClass
{
  GResolverClass parent_class;
};

GType lingmo-installer_mock_resolver_get_type (void) G_GNUC_CONST;

Lingmo-installerMockResolver *lingmo-installer_mock_resolver_new (void);

G_END_DECLS

#endif /* _LINGMO-INSTALLER_MOCK_RESOLVER_H */
