/* SPDX-License-Identifier: AGPL-3.0-or-later
 * FlekDeck client for Nyxian's append-only SYS_vroot ABI (765).
 * Completes the missing LiveShim/vroot.c in pinned source 350dd8db.
 */
#include <LiveShim/LiveShimSyscall.h>
#include <LiveShim/vroot.h>
#include <ksurface_abi.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

const char *liveshim_vroot(void)
{
    static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
    static char *root;
    pthread_mutex_lock(&lock);
    if (!root) {
        int64_t size = liveshim_syscall(SYS_vroot, (int64_t)0, (int64_t)0,
            (int64_t)0, (int64_t)0, (int64_t)0, (int64_t)0);
        if (size <= 0 || size > 65536) {
            if (size >= 0) errno = EOVERFLOW;
            pthread_mutex_unlock(&lock);
            return NULL;
        }
        char *buffer = calloc((size_t)size, 1);
        if (!buffer) {
            pthread_mutex_unlock(&lock);
            return NULL;
        }
        int64_t result = liveshim_syscall(SYS_vroot, (int64_t)(uintptr_t)buffer,
            (int64_t)size, (int64_t)0, (int64_t)0, (int64_t)0, (int64_t)0);
        if (result < 0 || !memchr(buffer, '\0', (size_t)size) || buffer[0] != '/') {
            free(buffer);
            pthread_mutex_unlock(&lock);
            if (result >= 0) errno = EINVAL;
            return NULL;
        }
        root = buffer;
    }
    const char *result = root;
    pthread_mutex_unlock(&lock);
    return result;
}
