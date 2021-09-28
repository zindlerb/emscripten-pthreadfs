#include <iostream>
#include <fstream>
#include <cstdio>
#include <emscripten.h>


int main()
{
  std::cout << "Start Rename test\n";

  // MEMFS file that is closed when renaming.

  std::ofstream closed_memfs_file;
  closed_memfs_file.open ("old_closed_memfs_file");
  closed_memfs_file << "Contents of closed_memfs_file.";
  closed_memfs_file.close();
 
  if (std::rename("old_closed_memfs_file", "new_closed_memfs_file")) {
    std::cout << "Error renaming closed_memfs_file\n";
    return 1;
  }
  std::cout << "Rename closed_memfs_file successfully\n";

  if(std::remove("new_closed_memfs_file")) {
    std::cout << "Removing closed_memfs_file failed\n";
    return 1;
  }
  std::cout << "Removed closed_memfs_file\n";

  // MEMFS file that is open when renaming.

  std::ofstream open_memfs_file;
  open_memfs_file.open ("old_open_memfs_file");
  open_memfs_file << "Contents of open_memfs_file.";
 
  if (std::rename("old_open_memfs_file", "new_open_memfs_file")) {
    std::cout << "Error renaming open_memfs_file\n";
    return 1;
  }
  std::cout << "Rename open_memfs_file successfully\n";
  open_memfs_file.close();

  if(std::remove("new_open_memfs_file")) {
    std::cout << "Removing open_memfs_file failed\n";
    return 1;
  }
  std::cout << "Removed open_memfs_file\n";

  // PThreadFS file that is closed when renaming.
  std::ofstream closed_pthreadfs_file;
  closed_pthreadfs_file.open ("persistent/old_closed_pthreadfs_file");
  closed_pthreadfs_file << "Contents of closed_pthreadfs_file.";
  closed_pthreadfs_file.close();
 
  if (std::rename("persistent/old_closed_pthreadfs_file", "persistent/new_closed_pthreadfs_file")) {
    std::cout << "Error renaming closed_pthreadfs_file\n";
    return 1;
  }
  std::cout << "Rename closed_pthreadfs_file successfully\n";
  closed_pthreadfs_file.close();

  if(std::remove("persistent/new_closed_pthreadfs_file")) {
    std::cout << "Removing closed_pthreadfs_file failed\n";
    return 1;
  }
  std::cout << "Removed closed_pthreadfs_file\n";

  // PThreadFS file that is open when renaming.
  std::ofstream open_pthreadfs_file;
  open_pthreadfs_file.open ("persistent/old_open_pthreadfs_file");
  open_pthreadfs_file << "Contents of open_pthreadfs_file.";
 
  if (std::rename("persistent/old_open_pthreadfs_file", "persistent/new_open_pthreadfs_file")) {
    std::cout << "Error renaming open_pthreadfs_file\n";
    return 1;
  }
  std::cout << "Rename open_pthreadfs_file successfully\n";
  open_pthreadfs_file.close();

  if(std::remove("persistent/new_open_pthreadfs_file")) {
    std::cout << "Removing open_pthreadfs_file failed.\n";
    std::cout << "This is expected when using the OPFS backend.\n";
    return 1;
  }
  std::cout << "Removed open_pthreadfs_file\n";

  std::cout << "Success\n";
}