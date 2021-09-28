// basic file operations
#include <iostream>
#include <fstream>
#include <string>
#include <emscripten.h>
#include "pthreadfs.h"

int main () {
  std::cout << "Proof that stdout works fine.\n";
  std::ofstream myfile;
  myfile.open ("persistent/example");
  myfile << "Writing a few characters.\n";
  myfile.close();

  std::string line;
  std::ifstream myfile_read ("persistent/example");
 
  if (myfile_read.is_open()) {
    std::getline(myfile_read, line);
    EM_ASM({console.log("Read line" + UTF8ToString($0));
    }, line.c_str());
    myfile_read.close();
  }

  std::ofstream stream1 ("persistent/multistreamexample");
  std::ofstream stream2 ("persistent/multistreamexample");
  stream1 << "Write a line through stream1.\n";
  stream2 << "Write a line through stream2.\n";
  stream1.close();
  stream2.close();

  std::remove("persistent/multistreamexample"); 
  bool can_open_deleted_file = (bool) std::ifstream("persistent/multistreamexample");
  if(!can_open_deleted_file) { 
    std::cout << "Opening deleted file failed, as expected.\n"; 
  }

  EM_ASM(console.log('after close'););
  EM_PTHREADFS_ASM( function timeout(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
    await timeout(3000);
    console.log("Promise resolving 3 seconds after closing the file");)
  EM_PTHREADFS_ASM( function timeout(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
    await timeout(1000);
    console.log("Promise resolving 1 second after the previous promise");
    console.log("Success");)
  return 0;
}
