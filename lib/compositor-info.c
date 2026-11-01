/* Print what the Wayland compositor says about itself that 10x's launcher
 * needs, one fact per line:
 *
 *   gpu MAJOR:MINOR   the device it composites on (linux-dmabuf feedback's
 *                     main device), the GPU native Wayland clients render on
 *   capabilities ...  the window actions it supports (xdg_toplevel
 *                     wm_capabilities): maximize, minimize, fullscreen,
 *                     window_menu. Toolkits hide title-bar buttons for
 *                     actions it doesn't offer.
 *
 * A fact the compositor doesn't advertise is left out. */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <wayland-client.h>
#include "linux-dmabuf-v1-client-protocol.h"
#include "xdg-shell-client-protocol.h"

static struct wl_compositor *compositor;
static struct xdg_wm_base *wm_base;
static struct zwp_linux_dmabuf_v1 *dmabuf;
static int pending;

static void registry_global(void *data, struct wl_registry *registry, uint32_t name,
                            const char *interface, uint32_t version)
{
    if (!strcmp(interface, wl_compositor_interface.name))
        compositor = wl_registry_bind(registry, name, &wl_compositor_interface, 1);
    else if (!strcmp(interface, xdg_wm_base_interface.name) && version >= 5)
        wm_base = wl_registry_bind(registry, name, &xdg_wm_base_interface, 5);
    else if (!strcmp(interface, zwp_linux_dmabuf_v1_interface.name) && version >= 4)
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

static void wm_base_ping(void *data, struct xdg_wm_base *base, uint32_t serial)
{
    xdg_wm_base_pong(base, serial);
}

static const struct xdg_wm_base_listener wm_base_listener = { wm_base_ping };

static void surface_configure(void *data, struct xdg_surface *surface, uint32_t serial)
{
    pending--;
}

static const struct xdg_surface_listener surface_listener = { surface_configure };

static void toplevel_configure(void *data, struct xdg_toplevel *toplevel, int32_t w, int32_t h,
                               struct wl_array *states) {}
static void toplevel_close(void *data, struct xdg_toplevel *toplevel) {}
static void toplevel_bounds(void *data, struct xdg_toplevel *toplevel, int32_t w, int32_t h) {}

static void toplevel_wm_capabilities(void *data, struct xdg_toplevel *toplevel, struct wl_array *caps)
{
    uint32_t *cap;

    fputs("capabilities", stdout);
    wl_array_for_each(cap, caps)
    {
        switch (*cap)
        {
        case XDG_TOPLEVEL_WM_CAPABILITIES_WINDOW_MENU: fputs(" window_menu", stdout); break;
        case XDG_TOPLEVEL_WM_CAPABILITIES_MAXIMIZE: fputs(" maximize", stdout); break;
        case XDG_TOPLEVEL_WM_CAPABILITIES_FULLSCREEN: fputs(" fullscreen", stdout); break;
        case XDG_TOPLEVEL_WM_CAPABILITIES_MINIMIZE: fputs(" minimize", stdout); break;
        }
    }
    putchar('\n');
}

static const struct xdg_toplevel_listener toplevel_listener =
{
    toplevel_configure, toplevel_close, toplevel_bounds, toplevel_wm_capabilities
};

int main(void)
{
    struct zwp_linux_dmabuf_feedback_v1 *feedback = NULL;
    struct xdg_toplevel *toplevel = NULL;
    struct xdg_surface *xdg_surface = NULL;
    struct wl_surface *surface = NULL;
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
    if (compositor && wm_base)
    {
        /* The capabilities come with a toplevel's first configure, which a
         * commit without a buffer asks for; nothing is ever shown. */
        xdg_wm_base_add_listener(wm_base, &wm_base_listener, NULL);
        surface = wl_compositor_create_surface(compositor);
        xdg_surface = xdg_wm_base_get_xdg_surface(wm_base, surface);
        xdg_surface_add_listener(xdg_surface, &surface_listener, NULL);
        toplevel = xdg_surface_get_toplevel(xdg_surface);
        xdg_toplevel_add_listener(toplevel, &toplevel_listener, NULL);
        xdg_toplevel_set_app_id(toplevel, "10x-compositor-info");
        wl_surface_commit(surface);
        pending++;
    }
    while (pending > 0 && wl_display_dispatch(display) != -1) continue;

    if (toplevel)
    {
        xdg_toplevel_destroy(toplevel);
        xdg_surface_destroy(xdg_surface);
        wl_surface_destroy(surface);
    }
    if (feedback) zwp_linux_dmabuf_feedback_v1_destroy(feedback);
    wl_display_roundtrip(display);
    wl_display_disconnect(display);
    return 0;
}
