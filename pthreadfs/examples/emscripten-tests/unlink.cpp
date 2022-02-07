/*
 * Copyright 2011 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#endif

static void create_file(const char *path, const char *buffer, int mode) {
  printf("creating: %s\n", path);
  int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err ==  (sizeof(char) * strlen(buffer)));

  close(fd);
}

void setup() {
  mkdir("/persistent/working", 0777);
#ifdef __EMSCRIPTEN__

#ifdef __EMSCRIPTEN_ASMFS__
  mkdir("working", 0777);
#else
  EM_ASM(
#if NODEFS
    FS.mount(NODEFS, { root: '.' }, 'working');
#endif
  );
#endif
#endif
  create_file("/persistent/working/file", "test", 0777);
  create_file("/persistent/working/file1", "test", 0777);
#ifdef WASMFS
  create_file("file-readonly", "test", 0555);
#else
  // Prefer to create the file as readable and then
  // use chmod.  See:
  // https://github.com/emscripten-core/emscripten/pull/15455
  create_file("/persistent/working/file-readonly", "test", 0777);
#endif
  mkdir("/persistent/working/dir-empty", 0777);
// TODO: delete this when chmod is implemented.
#ifndef WASMFS
  mkdir("/persistent/working/dir-readonly", 0777);
#else
  mkdir("dir-readonly", 0555);
#endif
  create_file("/persistent/working/dir-readonly/anotherfile", "test", 0777);
  mkdir("/persistent/working/dir-readonly/anotherdir", 0777);
#ifndef WASMFS
  chmod("/persistent/working/dir-readonly", 0555);
  chmod("/persistent/working/file-readonly", 0555);
#endif
  mkdir("/persistent/working/dir-full", 0777);
  create_file("/persistent/working/dir-full/anotherfile", "test", 0777);
}

void cleanup() {
  unlink("/persistent/working/file");
  unlink("/persistent/working/file1");
  rmdir("/persistent/working/dir-empty");
#ifndef WASMFS
  chmod("/persistent/working/dir-readonly", 0777);
  chmod("/persistent/working/file-readonly", 0777);
#endif
  unlink("/persistent/working/file-readonly");
  unlink("/persistent/working/dir-readonly/anotherfile");
  rmdir("/persistent/working/dir-readonly/anotherdir");
  rmdir("/persistent/working/dir-readonly");
  unlink("/persistent/working/dir-full/anotherfile");
  rmdir("/persistent/working/dir-full");
}

void test() {
  int err;
  char buffer[512];

  //
  // test unlink
  //
  err = unlink("/persistent/working/noexist");
  assert(err == -1);
  assert(errno == ENOENT);

  // Test non-existent parent
  err = unlink("/persistent/working/noexist/foo");
  assert(err == -1);
  assert(errno == ENOENT);

  // Test empty pathname
  err = unlink("");
  assert(err == -1);
  printf("%s\n", strerror(errno));
  assert(errno == ENOENT);

  err = unlink("/persistent/working/dir-readonly");
  assert(err == -1);

  // emscripten uses 'musl' what is an implementation of the standard library for Linux-based systems
#if defined(__linux__) || defined(__EMSCRIPTEN__)
  // Here errno is supposed to be EISDIR, but it is EPERM for NODERAWFS on macOS.
  // See issue #6121.
  assert(errno == EISDIR || errno == EPERM);
#else
  assert(errno == EPERM);
#endif

#ifndef SKIP_ACCESS_TESTS
  err = unlink("/persistent/working/dir-readonly/anotherfile");
  assert(err == -1);
  assert(errno == EACCES);
#endif

// TODO: Remove this when access is implemented.
#ifndef WASMFS
  err = access("/persistent/working/file1", F_OK);
  assert(!err);
#endif

  err = unlink("/persistent/working/file");
  assert(!err);
#ifndef WASMFS
  err = access("/persistent/working/file", F_OK);
  assert(err == -1);
#endif

  // Should be able to delete a read-only file.
  err = unlink("/persistent/working/file-readonly");
  assert(!err);

  //
  // test rmdir
  //
  err = rmdir("/persistent/working/noexist");
  assert(err == -1);
  assert(errno == ENOENT);

  err = rmdir("/persistent/working/file1");
  assert(err == -1);
  assert(errno == ENOTDIR);

#ifndef SKIP_ACCESS_TESTS
  err = rmdir("/persistent/working/dir-readonly/anotherdir");
  assert(err == -1);
  assert(errno == EACCES);
#endif

  err = rmdir("/persistent/working/dir-full");
  assert(err == -1);
  assert(errno == ENOTEMPTY);

  // test removing the cwd / root. The result isn't specified by
  // POSIX, but Linux seems to set EBUSY in both cases.
  // Update: Removing cwd on Linux does not return EBUSY.
  // WASMFS behaviour will match the native FS.
#ifndef __APPLE__
  getcwd(buffer, sizeof(buffer));
  err = rmdir(buffer);
  assert(err == -1);
#if defined(NODERAWFS) || defined(WASMFS)
  assert(errno == ENOTEMPTY);
#else
  assert(errno == EBUSY);
#endif
#endif
  err = rmdir("/");
  assert(err == -1);
#ifdef __APPLE__
  assert(errno == EISDIR);
#else
  // errno is EISDIR for NODERAWFS on macOS. See issue #6121.
  assert(errno == EBUSY || errno == EISDIR);
#endif

  err = rmdir("/persistent/working/dir-empty");
  assert(!err);
#ifndef WASMFS
  err = access("/persistent/working/dir-empty", F_OK);
  assert(err == -1);
#endif

  puts("success");
}

int main() {
  setup();
  test();
  cleanup();

  return EXIT_SUCCESS;
}
