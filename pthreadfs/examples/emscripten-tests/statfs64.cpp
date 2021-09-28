// basic file operations
#include <iostream>
#include <fstream>
#include <unistd.h>
#include <sys/statfs.h>
#include <string>
#include <emscripten.h>

int main () {
  std::cout << "Proof that stdout works fine.\n";
  std::ofstream myfile;
  myfile.open ("persistent/example");
  myfile << "Writing a few characters.\n";
  myfile.close();
  struct statfs sb;
  if((statfs("persistent/example",&sb))==0){
    std::cout << "total file nodes in fs are " << sb.f_files << "\n";
  }
  puts("Success");
  return 0;
}
