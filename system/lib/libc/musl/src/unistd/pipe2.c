#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include "syscall.h"

int pipe2(int fd[2], int flag)
{
	if (!flag) return pipe(fd);
	int ret = __syscall(SYS_pipe2, fd, flag);
	if (ret != -ENOSYS) return __syscall_ret(ret);
	ret = pipe(fd);
	if (ret) return ret;
#ifndef __EMSCRIPTEN__ // CLOEXEC makes no sense for a single process
	if (flag & O_CLOEXEC) {
		__syscall(SYS_fcntl, fd[0], F_SETFD, FD_CLOEXEC);
		__syscall(SYS_fcntl, fd[1], F_SETFD, FD_CLOEXEC);
	}
#endif
	if (flag & O_NONBLOCK) {
#ifdef __EMSCRIPTEN__
     __wasi_fd_fdstat_set_flags(fd[0], __WASI_FDFLAG_NONBLOCK);
     __wasi_fd_fdstat_set_flags(fd[1], __WASI_FDFLAG_NONBLOCK);
#else
		__syscall(SYS_fcntl, fd[0], F_SETFL, O_NONBLOCK);
		__syscall(SYS_fcntl, fd[1], F_SETFL, O_NONBLOCK);
#endif
	}
	return 0;
}
