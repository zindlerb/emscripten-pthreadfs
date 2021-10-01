/*
 * Copyright 2013 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <assert.h>
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void create_file(const char* path, const char* buffer, int mode) {
  int fd = open(path, O_WRONLY | O_CREAT, mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err == (sizeof(char) * strlen(buffer)));

  close(fd);
}

void setup() {
  int err;
  err = mkdir("persistent/filenametest", 0777);
  puts("filenametest");
  assert(!err);
  err = mkdir("persistent/folder space", 0777);
  puts("folder space");
  assert(!err);
  err = mkdir("persistent/folder_underscore", 0777);
  puts("folder_underscore");
  assert(!err);
}

void cleanup() {
  rmdir("persistent/folder space");
  rmdir("persistent/folder_underscore");
  rmdir("persistent/filenametest");
}

void test_file_contents(const char* path) {
  printf("Test contents for file %s\n", path);
  create_file(path, /*buffer=*/path, 0666);

  int fd = open(path, O_RDONLY, 0777);
  assert(fd >= 0);

  char readbuf[1000];
  int err = read(fd, readbuf, sizeof(char) * (strlen(path) + 1));
  assert(err > 0);
  printf("Content: %s\n", readbuf);
  close(fd);

  unlink(path);
}

void test_readdir(const char* path) {
  int err;
  DIR* directory_handle;
  struct dirent* directory_entry;
  int i;

  const char* filename = strrchr(path, '/') + 1;
  char* filename_lowercase = (char*)malloc(strlen(filename) + 1);
  strcpy(filename_lowercase, filename);
  for (int i = 0; filename_lowercase[i]; i++) {
    filename_lowercase[i] = tolower(filename_lowercase[i]);
  }

  int length_of_path = filename - path;
  char* folder = (char*)malloc(length_of_path + 1);
  memcpy(folder, path, length_of_path);
  folder[length_of_path] = '\0';

  printf("Test readdir for path %s\n", path);
  create_file(path, /*buffer=*/path, 0666);

  directory_handle = opendir(folder);
  assert(directory_handle);
  int seen_files[3] = {0, 0, 0};
  for (i = 0; i < 3; i++) {
    errno = 0;
    directory_entry = readdir(directory_handle);
    assert(directory_entry);
    assert(directory_entry->d_reclen == sizeof(*directory_entry));
    // Convert filenames to lowercase, since the system is supposed to be case-insensitive
    for (int i = 0; directory_entry->d_name[i]; i++) {
      directory_entry->d_name[i] = tolower(directory_entry->d_name[i]);
    }
    if (!seen_files[0] && !strcmp(directory_entry->d_name, ".")) {
      assert(directory_entry->d_type & DT_DIR);
      seen_files[0] = 1;
      continue;
    }
    if (!seen_files[1] && !strcmp(directory_entry->d_name, "..")) {
      assert(directory_entry->d_type & DT_DIR);
      seen_files[1] = 1;
      continue;
    }
    if (!seen_files[2] && !strcmp(directory_entry->d_name, filename_lowercase)) {
      assert(directory_entry->d_type & DT_REG);
      seen_files[2] = 1;
      continue;
    }
    assert(0 && "Found unexpected file in directory");
  }
  directory_entry = readdir(directory_handle);
  if (directory_entry)
    printf(
      "Unexpected path in directory found: %p : %s\n", directory_entry, directory_entry->d_name);
  assert(!directory_entry);

  err = closedir(directory_handle);
  assert(!err);

  unlink(path);
  free(folder);
  free(filename_lowercase);
}

int main() {
  setup();

  const char* paths[] = {"persistent/filenametest/file.txt",
    "persistent/filenametest/file with space", "persistent/filenametest/hyphen-file",
    "persistent/filenametest/underscore_file", "persistent/filenametest/UPPERCASE",
    "persistent/filenametest/mixedCASE", "persistent/filenametest/file!",
    "persistent/filenametest/file(parenthesis)", "persistent/filenametest/fileumlautäöüëé",
    "persistent/folder space/file", "persistent/folder_underscore/file"};

  for (size_t i = 0; i < sizeof(paths) / sizeof(paths[0]); i++) {
    test_file_contents(paths[i]);
    test_readdir(paths[i]);
  }
  cleanup();

  puts("success");
  return EXIT_SUCCESS;
}