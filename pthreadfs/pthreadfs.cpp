#include "pthreadfs.h"

#include <assert.h>
#include <emscripten.h>
#include <pthread.h>
#include <wasi/api.h>

#include <thread>
#include <functional>
#include <iostream>
#include <string>
#include <set>

#include <stdarg.h>

SyncToAsync::SyncToAsync() : thread(threadMain, this), childLock(mutex) {
  // The child lock is associated with the mutex, which takes the lock, and
  // we free it here. Only the child will lock/unlock it from now on.
  childLock.unlock();
}

SyncToAsync::~SyncToAsync() {
  quit = true;

  shutdown();

  thread.join();
}

void SyncToAsync::shutdown() {
  readyToWork = true;
  condition.notify_one();
}

void SyncToAsync::doWork(std::function<void(SyncToAsync::Callback)> newWork) {
  // Use the doWorkMutex to prevent more than one doWork being in flight at a
  // time, so that this is usable from multiple threads safely.
  std::lock_guard<std::mutex> doWorkLock(doWorkMutex);
  // Initialize the PThreadFS file system.
  if (!initialized) {
    {
    std::lock_guard<std::mutex> lock(mutex);
    work = [](SyncToAsync::Callback resume) {
      g_resumeFct = [resume]() { resume(); };
      init_pthreadfs(&resumeWrapper_v);
    };
    finishedWork = false;
    readyToWork = true;
    }
    condition.notify_one();

    // Wait for it to be complete.
    std::unique_lock<std::mutex> lock(mutex);
    condition.wait(lock, [&]() {
      return finishedWork;
    });
    initialized = true;
  }
  // Send the work over.
  {
    std::lock_guard<std::mutex> lock(mutex);
    work = newWork;
    finishedWork = false;
    readyToWork = true;
  }
  condition.notify_one();

  // Wait for it to be complete.
  std::unique_lock<std::mutex> lock(mutex);
  condition.wait(lock, [&]() {
    return finishedWork;
  });
}

void* SyncToAsync::threadMain(void* arg) {
  // Prevent the pthread from shutting down too early.
  EM_ASM(runtimeKeepalivePush(););
  auto* parent = (SyncToAsync*)arg;
  emscripten_async_call(threadIter, arg, 0);
  return 0;
}

void SyncToAsync::threadIter(void* arg) {
  auto* parent = (SyncToAsync*)arg;
  // Wait until we get something to do.
  parent->childLock.lock();
  parent->condition.wait(parent->childLock, [&]() {
    return parent->readyToWork;
  });
  if (parent->quit) {
    EM_ASM(runtimeKeepalivePop(););
    return;
  }
  auto work = parent->work;
  parent->readyToWork = false;
  // Do the work.
  work([parent, arg]() {
    // We are called, so the work was finished. Notify the caller.
    parent->finishedWork = true;
    parent->childLock.unlock();
    parent->condition.notify_one();
    threadIter(arg);
  });
}

// Define global variables to be populated by resume;
SyncToAsync::Callback g_resumeFct;
SyncToAsync g_synctoasync_helper;

// Static functions calling resumFct and setting the return value.
void resumeWrapper_v()
{
  g_resumeFct();
}
// return value long
long resume_result_long = 0;
void resumeWrapper_l(long retVal)
{
  resume_result_long = retVal;
  g_resumeFct();
}
// return value __wasi_errno_t
__wasi_errno_t resume_result_wasi = 0;
void resumeWrapper_wasi(__wasi_errno_t retVal)
{
  resume_result_wasi = retVal;
  g_resumeFct();
}

// File System Access collection
std::set<long> fsa_file_descriptors;
std::set<std::string> mounted_directories;

// Wasi definitions
WASI_CAPI_DEF(write, const __wasi_ciovec_t *iovs, size_t iovs_len, __wasi_size_t *nwritten) {
  WASI_SYNCTOASYNC(write, iovs, iovs_len, nwritten);
}

WASI_CAPI_DEF(read, const __wasi_iovec_t *iovs, size_t iovs_len, __wasi_size_t *nread) {
  WASI_SYNCTOASYNC(read, iovs, iovs_len, nread);
}
WASI_CAPI_DEF(pwrite, const __wasi_ciovec_t *iovs, size_t iovs_len, __wasi_filesize_t offset, __wasi_size_t *nwritten) {
  WASI_SYNCTOASYNC(pwrite, iovs, iovs_len, offset, nwritten);
}
WASI_CAPI_DEF(pread, const __wasi_iovec_t *iovs, size_t iovs_len, __wasi_filesize_t offset, __wasi_size_t *nread) {
  WASI_SYNCTOASYNC(pread, iovs, iovs_len, offset, nread);
}
WASI_CAPI_DEF(seek, __wasi_filedelta_t offset, __wasi_whence_t whence, __wasi_filesize_t *newoffset) {
  WASI_SYNCTOASYNC(seek, offset, whence, newoffset);
}
WASI_CAPI_DEF(fdstat_get, __wasi_fdstat_t *stat) {
  WASI_SYNCTOASYNC(fdstat_get, stat);
}
WASI_CAPI_NOARGS_DEF(close) {
  if(fsa_file_descriptors.count(fd) > 0) {
     g_synctoasync_helper.doWork([fd](SyncToAsync::Callback resume) { 
      g_resumeFct = [resume]() { resume(); };
      __fd_close_async(fd, &resumeWrapper_wasi); 
      });
    if (resume_result_wasi == __WASI_ERRNO_SUCCESS) {
      fsa_file_descriptors.erase(fd);
    }
    return resume_result_wasi;
  } 
  return fd_close(fd);
}
WASI_CAPI_NOARGS_DEF(sync) {
  WASI_SYNCTOASYNC_NOARGS(sync);
}

// Syscall definitions
SYS_CAPI_DEF(open, 5, long path, long flags, ...) {
  
  std::string pathname((char*) path);
  if (pathname.rfind("/pthreadfs", 0) == 0 || pathname.rfind("pthreadfs", 0) == 0) {
    va_list vl;
    va_start(vl, flags);
    mode_t mode = va_arg(vl, mode_t);
    va_end(vl);
    SYS_SYNCTOASYNC_NORETURN(open, path, flags, mode);
    fsa_file_descriptors.insert(resume_result_long);
    return resume_result_long;
  }
  va_list vl;
  va_start(vl, flags);
  long res = __sys_open(path, flags, (int) vl);
  va_end(vl);
  return res;
}

SYS_CAPI_DEF(unlink, 10, long path) {
  SYS_SYNCTOASYNC_PATH(unlink, path);
}

SYS_CAPI_DEF(chdir, 12, long path) {
  SYS_SYNCTOASYNC_PATH(chdir, path);
}

SYS_CAPI_DEF(mknod, 14, long path, long mode, long dev) {
  SYS_SYNCTOASYNC_PATH(mknod, path, mode, dev);
}

SYS_CAPI_DEF(chmod, 15, long path, long mode) {
  SYS_SYNCTOASYNC_PATH(chmod, path, mode);
}

SYS_CAPI_DEF(access, 33, long path, long amode) {
  SYS_SYNCTOASYNC_PATH(access, path, amode);
}

SYS_CAPI_DEF(rename, 38, long old_path, long new_path) {
  std::string old_pathname((char*) old_path);
  std::string new_pathname((char*) new_path);

  if (old_pathname.rfind("/pthreadfs", 0) == 0 || old_pathname.rfind("pthreadfs", 0) == 0) {
    if (new_pathname.rfind("/pthreadfs", 0) == 0 || new_pathname.rfind("pthreadfs", 0) == 0) {
      SYS_SYNCTOASYNC_NORETURN(rename, old_path, new_path);
      return resume_result_long;
    }
    return EXDEV;
  }
  if (new_pathname.rfind("/pthreadfs", 0) == 0 || new_pathname.rfind("pthreadfs", 0) == 0) {
    return EXDEV;
  }
  long res = __sys_rename(old_path, new_path);
  return res;
}

SYS_CAPI_DEF(mkdir, 39, long path, long mode) {
  SYS_SYNCTOASYNC_PATH(mkdir, path, mode);
}

SYS_CAPI_DEF(rmdir, 40, long path) {
  SYS_SYNCTOASYNC_PATH(rmdir, path);
}

SYS_CAPI_DEF(ioctl, 54, long fd, long request, ...) {
  void *arg;
	va_list ap;
	va_start(ap, request);
	arg = va_arg(ap, void *);
	va_end(ap);
  
  SYS_SYNCTOASYNC_FD(ioctl, fd, request, arg);
}

SYS_CAPI_DEF(readlink, 85, long path, long buf, long bufsize) {
  SYS_SYNCTOASYNC_PATH(readlink, path, buf, bufsize);
}

SYS_CAPI_DEF(fchmod, 94, long fd, long mode) {
  SYS_SYNCTOASYNC_FD(fchmod, fd, mode);
}

SYS_CAPI_DEF(fchdir, 133, long fd) {
  SYS_SYNCTOASYNC_FD(fchdir, fd);
}

SYS_CAPI_DEF(fdatasync, 148, long fd) {
  SYS_SYNCTOASYNC_FD(fdatasync, fd);
}

SYS_CAPI_DEF(truncate64, 193, long path, long zero, long low, long high) {
  SYS_SYNCTOASYNC_PATH(truncate64, path, zero, low, high);
}

SYS_CAPI_DEF(ftruncate64, 194, long fd, long zero, long low, long high) {
  SYS_SYNCTOASYNC_FD(ftruncate64, fd, zero, low, high);
}

SYS_CAPI_DEF(stat64, 195, long path, long buf) {
  SYS_SYNCTOASYNC_PATH(stat64, path, buf);
}

SYS_CAPI_DEF(lstat64, 196, long path, long buf) {
  SYS_SYNCTOASYNC_PATH(lstat64, path, buf);
}

SYS_CAPI_DEF(fstat64, 197, long fd, long buf) {
  SYS_SYNCTOASYNC_FD(fstat64, fd, buf);
}

SYS_CAPI_DEF(lchown32, 198, long path, long owner, long group) {
  SYS_SYNCTOASYNC_PATH(lchown32, path, owner, group);
}

SYS_CAPI_DEF(fchown32, 207, long fd, long owner, long group) {
  SYS_SYNCTOASYNC_FD(fchown32, fd, owner, group);
}

SYS_CAPI_DEF(chown32, 212, long path, long owner, long group) {
  SYS_SYNCTOASYNC_PATH(chown32, path, owner, group);
}

SYS_CAPI_DEF(getdents64, 220, long fd, long dirp, long count) {
  SYS_SYNCTOASYNC_FD(getdents64, fd, dirp, count);
}

SYS_CAPI_DEF(fcntl64, 221, long fd, long cmd, ...) {
  
  if (fsa_file_descriptors.count(fd) > 0) { 
    // varargs are currently unused by __sys_fcntl64_async.
    va_list vl;
    va_start(vl, cmd);
    int varargs = va_arg(vl, int);
    va_end(vl);
    g_synctoasync_helper.doWork([fd, cmd, varargs](SyncToAsync::Callback resume) {
      g_resumeFct = [resume]() { 
        resume(); 
      };
      __sys_fcntl64_async(fd, cmd, varargs, &resumeWrapper_l);
    });
    return resume_result_long; 
  } 
  va_list vl;
  va_start(vl, cmd);
  long res =  __sys_fcntl64(fd, cmd, (int) vl);
  va_end(vl);
  return res;
}

SYS_CAPI_DEF(statfs64, 268, long path, long size, long buf) {
  SYS_SYNCTOASYNC_PATH(statfs64, path, size, buf);
}

SYS_CAPI_DEF(fstatfs64, 269, long fd, long size, long buf) {
  SYS_SYNCTOASYNC_FD(fstatfs64, fd, size, buf);
}

SYS_CAPI_DEF(fallocate, 324, long fd, long mode, long off_low, long off_high, long len_low, long len_high) {
  SYS_SYNCTOASYNC_FD(fallocate, fd, mode, off_low, off_high, len_low, len_high);
}

// Other helper code

void emscripten_init_pthreadfs() {
  EM_ASM(console.log('Calling emscripten_init_pthreadfs() is no longer necessary'););
  return;
}
