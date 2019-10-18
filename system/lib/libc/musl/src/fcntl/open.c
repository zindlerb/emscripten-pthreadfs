#include <fcntl.h>
#include <stdarg.h>
#include "syscall.h"
#include "libc.h"

int open(const char *filename, int flags, ...)
{
	mode_t mode = 0;

	if ((flags & O_CREAT) || (flags & O_TMPFILE) == O_TMPFILE) {
		va_list ap;
		va_start(ap, flags);
		mode = va_arg(ap, mode_t);
		va_end(ap);
	}

#ifdef __EMSCRIPTEN__
	int fd = emscripten_path_open(filename, flags, mode);
	// CLOEXEC makes no sense for a single process
#else
	int fd = __sys_open_cp(filename, flags, mode);
	if (fd>=0 && (flags & O_CLOEXEC))
		__syscall(SYS_fcntl, fd, F_SETFD, FD_CLOEXEC);
#endif

	return __syscall_ret(fd);
}

LFS64(open);
