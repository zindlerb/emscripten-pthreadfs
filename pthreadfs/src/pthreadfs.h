#ifndef PTHREADFS_H
#define PTHREADFS_H

#include <wasi/api.h>
#include <thread>

#define EM_PTHREADFS_ASM(code) g_synctoasync_helper.doWork([](SyncToAsync::Callback resume) { \
    g_resumeFct = [resume]() { resume(); }; \
    EM_ASM({(async () => {code wasmTable.get($0)(); \
    })();}, &resumeWrapper_v); \
  });

#define WASI_JSAPI_DEF(name, ...) \
  extern void __fd_##name##_async(__wasi_fd_t fd, __VA_ARGS__, void (*fun)(__wasi_errno_t)); \
  extern __wasi_errno_t fd_##name(__wasi_fd_t fd, __VA_ARGS__);
#define WASI_JSAPI_NOARGS_DEF(name) \
  extern void __fd_##name##_async(__wasi_fd_t fd, void (*fun)(__wasi_errno_t)); \
  extern __wasi_errno_t fd_##name(__wasi_fd_t fd);

#define WASI_CAPI_DEF(name, ...) __wasi_errno_t __wasi_fd_##name(__wasi_fd_t fd, __VA_ARGS__)
#define WASI_CAPI_NOARGS_DEF(name) __wasi_errno_t __wasi_fd_##name(__wasi_fd_t fd)

#define WASI_SYNCTOASYNC(name, ...) \
  if(fsa_file_descriptors.count(fd) > 0) { \
    g_synctoasync_helper.doWork([fd, __VA_ARGS__](SyncToAsync::Callback resume) { \
      g_resumeFct = [resume]() { resume(); }; \
      __fd_##name##_async(fd, __VA_ARGS__, &resumeWrapper_wasi); \
    }); \
    return resume_result_wasi; \
  } \
  return fd_##name(fd, __VA_ARGS__);
#define WASI_SYNCTOASYNC_NOARGS(name) \
  if(fsa_file_descriptors.count(fd) > 0) { \
    g_synctoasync_helper.doWork([fd](SyncToAsync::Callback resume) { \
      g_resumeFct = [resume]() { resume(); }; \
      __fd_##name##_async(fd, &resumeWrapper_wasi); \
    }); \
    return resume_result_wasi; \
  } \
  return fd_##name(fd);

// Classic Syscalls

#define SYS_JSAPI_DEF(name, ...) \
  extern void __sys_##name##_async(__VA_ARGS__, void (*fun)(long)); \
  extern long __sys_##name(__VA_ARGS__);

#define SYS_JSAPI_NOARGS_DEF(name) \
  extern void __sys_##name##_async(void (*fun)(long)); \
  extern long __sys_##name();

#define SYS_CAPI_DEF(name, number, ...) long __syscall##number(__VA_ARGS__)

#define SYS_DEF(name, number, ...) SYS_CAPI_DEF(name, number, __VA_ARGS__); SYS_JSAPI_DEF(name, __VA_ARGS__)

#define SYS_JSAPI(name, ...) __sys_##name##_async(__VA_ARGS__)
#define SYS_SYNCTOASYNC_NORETURN(name, ...) g_synctoasync_helper.doWork([__VA_ARGS__](SyncToAsync::Callback resume) { \
    g_resumeFct = [resume]() { resume(); }; \
    SYS_JSAPI(name, __VA_ARGS__, &resumeWrapper_l); \
  });
#define SYS_SYNCTOASYNC_FD(name, ...) \
  if(fsa_file_descriptors.count(fd) > 0) { \
    g_synctoasync_helper.doWork([__VA_ARGS__](SyncToAsync::Callback resume) { \
      g_resumeFct = [resume]() { resume(); }; \
      __sys_##name##_async(__VA_ARGS__, &resumeWrapper_l); \
    }); \
    return resume_result_long; \
  } \
  return __sys_##name(__VA_ARGS__);
#define SYS_SYNCTOASYNC_PATH(name, ...) \
  std::string pathname((char*) path); \
  if (pathname.rfind("/filesystemaccess", 0) == 0 || pathname.rfind("filesystemaccess", 0) == 0) { \
    g_synctoasync_helper.doWork([__VA_ARGS__](SyncToAsync::Callback resume) { \
      g_resumeFct = [resume]() { resume(); }; \
      __sys_##name##_async(__VA_ARGS__, &resumeWrapper_l); \
    }); \
    return resume_result_long; \
  } \
  return __sys_##name(__VA_ARGS__);

extern "C" {
  // Helpers
  extern void init_pthreadfs(void (*fun)(void));
  extern void init_sfafs(void (*fun)(void));
  extern void init_fsafs(void (*fun)(void));
  void emscripten_init_pthreadfs();

  // WASI
  WASI_JSAPI_DEF(write, const __wasi_ciovec_t *iovs, size_t iovs_len, __wasi_size_t *nwritten)
  WASI_JSAPI_DEF(read, const __wasi_iovec_t *iovs, size_t iovs_len, __wasi_size_t *nread)
  WASI_JSAPI_DEF(pwrite, const __wasi_ciovec_t *iovs, size_t iovs_len, __wasi_filesize_t offset, __wasi_size_t *nwritten)
  WASI_JSAPI_DEF(pread, const __wasi_iovec_t *iovs, size_t iovs_len, __wasi_filesize_t offset, __wasi_size_t *nread)
  WASI_JSAPI_DEF(seek, __wasi_filedelta_t offset, __wasi_whence_t whence, __wasi_filesize_t *newoffset)
  WASI_JSAPI_DEF(fdstat_get, __wasi_fdstat_t *stat)
  WASI_JSAPI_NOARGS_DEF(close)
  WASI_JSAPI_NOARGS_DEF(sync)

  // Syscalls
  // see https://github.com/emscripten-core/emscripten/blob/main/system/lib/libc/musl/arch/emscripten/syscall_arch.h
SYS_CAPI_DEF(open, 5, long path, long flags, ...);
SYS_JSAPI_DEF(open, long path, long flags, int varargs)

SYS_CAPI_DEF(unlink, 10, long path);
SYS_JSAPI_DEF(unlink, long path)

SYS_CAPI_DEF(chdir, 12, long path);
SYS_JSAPI_DEF(chdir, long path)

SYS_CAPI_DEF(mknod, 14, long path, long mode, long dev);
SYS_JSAPI_DEF(mknod, long path, long mode, long dev)

SYS_CAPI_DEF(chmod, 15, long path, long mode);
SYS_JSAPI_DEF(chmod, long path, long mode)

SYS_CAPI_DEF(access, 33, long path, long amode);
SYS_JSAPI_DEF(access, long path, long amode)

SYS_CAPI_DEF(mkdir, 39, long path, long mode);
SYS_JSAPI_DEF(mkdir, long path, long mode)

SYS_CAPI_DEF(rmdir, 40, long path);
SYS_JSAPI_DEF(rmdir, long path)

SYS_CAPI_DEF(ioctl, 54, long fd, long request, ...);
SYS_JSAPI_DEF(ioctl, long fd, long request, void *const varargs)

SYS_CAPI_DEF(readlink, 85, long path, long buf, long bufsize);
SYS_JSAPI_DEF(readlink, long path, long buf, long bufsize)

SYS_CAPI_DEF(fchmod, 94, long fd, long mode);
SYS_JSAPI_DEF(fchmod, long fd, long mode)

SYS_CAPI_DEF(fchdir, 133, long fd);
SYS_JSAPI_DEF(fchdir, long fd)

SYS_CAPI_DEF(fdatasync, 148, long fd);
SYS_JSAPI_DEF(fdatasync, long fd)

SYS_CAPI_DEF(truncate64, 193, long path, long zero, long low, long high);
SYS_JSAPI_DEF(truncate64, long path, long zero, long low, long high)

SYS_CAPI_DEF(ftruncate64, 194, long fd, long zero, long low, long high);
SYS_JSAPI_DEF(ftruncate64, long fd, long zero, long low, long high)

SYS_CAPI_DEF(stat64, 195, long path, long buf);
SYS_JSAPI_DEF(stat64, long path, long buf)

SYS_CAPI_DEF(lstat64, 196, long path, long buf);
SYS_JSAPI_DEF(lstat64, long path, long buf)

SYS_CAPI_DEF(fstat64, 197, long fd, long buf);
SYS_JSAPI_DEF(fstat64, long fd, long buf)

SYS_CAPI_DEF(lchown32, 198, long path, long owner, long group);
SYS_JSAPI_DEF(lchown32, long path, long owner, long group)

SYS_CAPI_DEF(fchown32, 207, long fd, long owner, long group);
SYS_JSAPI_DEF(fchown32, long fd, long owner, long group)

SYS_CAPI_DEF(chown32, 212, long path, long owner, long group);
SYS_JSAPI_DEF(chown32, long path, long owner, long group)

SYS_CAPI_DEF(getdents64, 220, long fd, long dirp, long count);
SYS_JSAPI_DEF(getdents64, long fd, long dirp, long count)

SYS_CAPI_DEF(fcntl64, 221, long fd, long cmd, ...);
SYS_JSAPI_DEF(fcntl64, long fd, long cmd, int varargs)

SYS_CAPI_DEF(statfs64, 268, long path, long size, long buf);
SYS_JSAPI_DEF(statfs64, long path, long size, long buf)

SYS_CAPI_DEF(fstatfs64, 269, long fd, long size, long buf);
SYS_JSAPI_DEF(fstatfs64, long fd, long size, long buf)

SYS_CAPI_DEF(fallocate, 324, long fd, long mode, long off_low, long off_high, long len_low, long len_high);
SYS_JSAPI_DEF(fallocate, long fd, long mode, long off_low, long off_high, long len_low, long len_high)

}

class SyncToAsync {
public:
  using Callback = std::function<void()>;

  SyncToAsync();

  ~SyncToAsync();

  void shutdown();

  // Run some work on thread. This is a synchronous call, but the thread can do
  // async work for us. To allow us to know when the async work finishes, the
  // worker is given a function to call at that time.
  //
  // It is safe to call this method from multiple threads, as it locks itself.
  // That is, you can create an instance of this and call it from multiple
  // threads freely.
  void doWork(std::function<void(Callback)> newWork);

private:
  std::thread thread;
  std::mutex mutex;
  std::mutex doWorkMutex;
  std::condition_variable condition;
  std::function<void(Callback)> work;
  bool readyToWork = false;
  bool finishedWork;
  bool quit = false;

  // The child will be asynchronous, and therefore we cannot rely on RAII to
  // unlock for us, we must do it manually.
  std::unique_lock<std::mutex> childLock;

  static void* threadMain(void* arg);

  static void threadIter(void* arg);
};

// Declare global variables to be populated by resume;
extern SyncToAsync::Callback g_resumeFct;
extern SyncToAsync g_synctoasync_helper;

// Static functions calling resumFct and setting corresponding the return value.
void resumeWrapper_v();

void resumeWrapper_l(long retVal);

void resumeWrapper_wasi(__wasi_errno_t retVal);

#endif  // PTHREADFS_H