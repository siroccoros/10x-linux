/* Print what the Wayland compositor says about itself that 10x's launcher
 * needs, one fact per line:
 *
 *   gpu MAJOR:MINOR   the device it composites on (linux-dmabuf feedback's
 *                     main device), the GPU native Wayland clients render on
 *
 * A fact the compositor doesn't advertise is left out. */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <wayland-client.h>
#include "linux-dmabuf-v1-client-protocol.h"

static struct zwp_linux_dmabuf_v1 *dmabuf;
static int pending;

static void registry_global(void *data, struct wl_registry *registry, uint32_t name,
                            const char *interface, uint32_t version)
{
    if (!strcmp(interface, zwp_linux_dmabuf_v1_interface.name) && version >= 4)
        dmabuf = wl_registry_bind(registry, name, &zwp_linux_dmabuf_v1_interface, 4);
}

static void registry_global_remove(void *data, struct wl_registry *registry, uint32_t name) {}

static const struct wl_registry_listener registry_listener = { registry_global, registry_global_remove };

static void feedback_done(void *data, struct zwp_linux_dmabuf_feedback_v1 *feedback)
{
    pending--;
}

static void feedback_format_table(void *data, struct zwp_linux_dmabuf_feedback_v1 *feedback,
                                  int32_t fd, uint32_t size)
{
    close(fd);
}

static void feedback_main_device(void *data, struct zwp_linux_dmabuf_feedback_v1 *feedback,
                                 struct wl_array *device)
{
    dev_t dev;

    if (device->size != sizeof(dev)) return;
    memcpy(&dev, device->data, sizeof(dev));
    printf("gpu %u:%u\n", major(dev), minor(dev));
}

static void feedback_tranche_done(void *data, struct zwp_linux_dmabuf_feedback_v1 *feedback) {}
static void feedback_tranche_target_device(void *data, struct zwp_linux_dmabuf_feedback_v1 *feedback,
                                           struct wl_array *device) {}
static void feedback_tranche_formats(void *data, struct zwp_linux_dmabuf_feedback_v1 *feedback,
                                     struct wl_array *indices) {}
static void feedback_tranche_flags(void *data, struct zwp_linux_dmabuf_feedback_v1 *feedback,
                                   uint32_t flags) {}

static const struct zwp_linux_dmabuf_feedback_v1_listener feedback_listener =
{
    feedback_done, feedback_format_table, feedback_main_device, feedback_tranche_done,
    feedback_tranche_target_device, feedback_tranche_formats, feedback_tranche_flags
};

int main(void)
{
    struct zwp_linux_dmabuf_feedback_v1 *feedback = NULL;
    struct wl_display *display;

    if (!(display = wl_display_connect(NULL))) return 1;
    wl_registry_add_listener(wl_display_get_registry(display), &registry_listener, NULL);
    wl_display_roundtrip(display);

    if (dmabuf)
    {
        feedback = zwp_linux_dmabuf_v1_get_default_feedback(dmabuf);
        zwp_linux_dmabuf_feedback_v1_add_listener(feedback, &feedback_listener, NULL);
        pending++;
    }
    while (pending > 0 && wl_display_dispatch(display) != -1) continue;

    if (feedback) zwp_linux_dmabuf_feedback_v1_destroy(feedback);
    wl_display_roundtrip(display);
    wl_display_disconnect(display);
    return 0;
}
