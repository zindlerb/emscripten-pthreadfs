/*
 * Copyright 2021 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */


#include <assert.h>
#include <fstream>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include "pthreadfs.h"

struct file_info {
 public:
  file_info(std::string path, std::string first_line, int size): path_(path), first_line_(first_line), size_(size) {} 
  std::string path_;
  std::string first_line_;
  int size_;
};

void test(void* arg) {
  file_info* file = (file_info*) arg;
  std::cout << "Start reading first line of file " << file->path_ << std::endl;
  std::ifstream stream(file->path_);
  std::string read_line;
  std::getline(stream, read_line);
  stream.close();

  std::cout << "  " << read_line << std::endl;
  assert(read_line == file->first_line_);

  struct stat s;
  int err = stat(file->path_.c_str(), &s);
  assert(!err);
  assert(s.st_size == file->size_);
  
  std::cout << "Success.\n";
}

int main() {
  std::cout << "Do some work before loading files.\n";

  file_info* small_file  = new file_info("persistent/intermediate_loading/smallfile.txt", "These are the contents of a very small file.", 188);
  file_info* medium_file  = new file_info("persistent/intermediate_loading/subfolder/mediumfile.txt",
    "Begin mediumfile.txt -------------------------------------------", 138670);
  file_info* big_file  = new file_info("persistent/intermediate_loading/bigfile.txt", "Begin bigfile.txt ----------------------------------------------",
    212992000);

  EM_ASM({
    importScripts("pkg_intermediate_small.js");
    PThreadFS.init('persistent').then(async () => {
      let load_fct = Module["pthreadfs_available_packages"].pop();
      await load_fct(); 

      // Load the second function.
      importScripts("pkg_intermediate_mediumlarge.js");
      PThreadFS.init('persistent').then(async () => {
        let load_fct = Module["pthreadfs_available_packages"].pop();
        await load_fct(); 
      });
    });
  });
  // Wait 1 second for loading the small package.
  emscripten_async_call(test, small_file, 1000);

  // Wait another second for loading the larger package.
  emscripten_async_call(test, medium_file, 2000);
  emscripten_async_call(test, big_file, 2000);

  return 0;
}