#include <stdio.h>
#include <emscripten/em_asm.h>

void out(const char* msg) {
  EM_ASM({ console.log(UTF8ToString($0)); }, msg);
}

// Test that stdout/printf and console.log message are interleaved as expected
// and all arrive at the console.
// See https://github.com/emscripten-core/emscripten/issues/14804
int main() {
  printf("printf 1\n");
  out("console.log 1");
  printf("printf 2\n");
  out("console.log 2");
  printf("printf 3\n");
  out("console.log 3");
  printf("done\n");
  return 0;
}
