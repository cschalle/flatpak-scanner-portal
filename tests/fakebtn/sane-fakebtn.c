/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* A SANE backend for testing the buttons of a scanner, and nothing else. It has one scanner with two
 * sensor options, "scan" and "intelliscan", which read a file in $FAKEBTN_DIR with that name: "1" is
 * a button that is down, "L" one that reads true once and then releases itself, as backends do that
 * latch, and anything else is released. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sane/sane.h>

static const SANE_Device device = { "fakebtn:0", "Fake", "Button Scanner", "flatbed scanner" };
static const SANE_Device *devices[] = { &device, NULL };
static const char *names[] = { "scan", "intelliscan" };

static SANE_Option_Descriptor descriptors[3];

SANE_Status sane_fakebtn_init (SANE_Int *version, SANE_Auth_Callback cb) { if (version) *version = SANE_VERSION_CODE (1, 0, 0); return SANE_STATUS_GOOD; }
void sane_fakebtn_exit (void) {}
SANE_Status sane_fakebtn_get_devices (const SANE_Device ***list, SANE_Bool local) { *list = devices; return SANE_STATUS_GOOD; }
SANE_Status sane_fakebtn_open (SANE_String_Const name, SANE_Handle *handle) { if (strcmp (name, "fakebtn:0") != 0) return SANE_STATUS_INVAL; *handle = (SANE_Handle) &device; return SANE_STATUS_GOOD; }
void sane_fakebtn_close (SANE_Handle handle) {}

const SANE_Option_Descriptor *
sane_fakebtn_get_option_descriptor (SANE_Handle handle, SANE_Int option)
{
  if (option < 0 || option > 2)
    return NULL;
  memset (&descriptors[option], 0, sizeof descriptors[option]);
  descriptors[option].size = sizeof (SANE_Word);
  if (option == 0)
    {
      descriptors[0].title = descriptors[0].desc = "Number of options";
      descriptors[0].type = SANE_TYPE_INT;
      descriptors[0].cap = SANE_CAP_SOFT_DETECT;
    }
  else
    {
      descriptors[option].name = names[option - 1];
      descriptors[option].title = descriptors[option].desc = names[option - 1];
      descriptors[option].type = SANE_TYPE_BOOL;
      descriptors[option].cap = SANE_CAP_SOFT_DETECT | SANE_CAP_HARD_SELECT;
    }
  return &descriptors[option];
}

SANE_Status
sane_fakebtn_control_option (SANE_Handle handle, SANE_Int option, SANE_Action action, void *value, SANE_Int *info)
{
  char path[4096], contents[8] = "";
  const char *dir = getenv ("FAKEBTN_DIR");
  FILE *f;

  if (info)
    *info = 0;
  if (option < 0 || option > 2 || action != SANE_ACTION_GET_VALUE)
    return SANE_STATUS_INVAL;
  if (option == 0)
    {
      *(SANE_Word *) value = 3;
      return SANE_STATUS_GOOD;
    }
  *(SANE_Word *) value = 0;
  if (dir == NULL)
    return SANE_STATUS_GOOD;
  snprintf (path, sizeof path, "%s/%s", dir, names[option - 1]);
  f = fopen (path, "r");
  if (f == NULL)
    return SANE_STATUS_GOOD;
  if (fgets (contents, sizeof contents, f) == NULL)
    contents[0] = 0;
  fclose (f);
  if (contents[0] == '1')
    *(SANE_Word *) value = 1;
  else if (contents[0] == 'L')
    {
      *(SANE_Word *) value = 1;
      f = fopen (path, "w");
      if (f)
        {
          fputs ("0", f);
          fclose (f);
        }
    }
  return SANE_STATUS_GOOD;
}

SANE_Status sane_fakebtn_get_parameters (SANE_Handle h, SANE_Parameters *p) { return SANE_STATUS_INVAL; }
SANE_Status sane_fakebtn_start (SANE_Handle h) { return SANE_STATUS_INVAL; }
SANE_Status sane_fakebtn_read (SANE_Handle h, SANE_Byte *d, SANE_Int m, SANE_Int *l) { *l = 0; return SANE_STATUS_EOF; }
void sane_fakebtn_cancel (SANE_Handle h) {}
SANE_Status sane_fakebtn_set_io_mode (SANE_Handle h, SANE_Bool n) { return SANE_STATUS_UNSUPPORTED; }
SANE_Status sane_fakebtn_get_select_fd (SANE_Handle h, SANE_Int *fd) { return SANE_STATUS_UNSUPPORTED; }
