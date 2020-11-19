var z = fleefl();

var zz = fleefl();

var keeperObj = {
 x: fleefl()
};

var keeperArray = [ 1, 2, "3", four() ];

function g(a) {
 return a + 1;
}

Module["g"] = g;

function h(a) {
 return a + 1;
}

print(h(123));

(function() {
 var z = fleefl();
 var zz = fleefl();
 function g(a) {
  return a + 1;
 }
 Module["g"] = g;
 function hh(a) {
  return a + 1;
 }
 print(hh(123));
})();

function glue() {
 function lookup() {
  throw 1;
 }
}

glue();

function _glCreateShader() {
 return 1;
}

function emulate() {
 _glCreateShader = function _glCreateShader(shaderType) {
  return glCreateShader();
 };
}

emulate();

___cxa_find_matching_catch_before();

function ___cxa_find_matching_catch_before() {
 if (!___cxa_find_matching_catch_before.buffer) ___cxa_find_matching_catch_before.buffer = {};
}

function ___cxa_find_matching_catch_after() {
 if (!___cxa_find_matching_catch_after.buffer) ___cxa_find_matching_catch_after.buffer = {};
}

___cxa_find_matching_catch_after();

var dotOther = Side.effect;

var FS = {
 foo: function(stream, offset, length) {
  stream.allocate;
  FS;
  for (var __exportedFunc in asm) {
   var jsname = __exportedFunc;
   global_object[jsname] = Module[jsname] = asm[__exportedFunc];
  }
 }
};

var readWrite;

function doWrites(dummy) {
 null;;
 null;;
 readWrite = 30;
 doWrites(readWrite);
}

Module.doWrites = doWrites;

function foo() {
 null;;
}

Module.foo = foo;

function _glIsEnabled1(x0) {}

function foo1() {
 _glIsEnabled1 = null;;
 _glIsEnabled1();
}

Module.foo1 = foo1;

var _emscripten_glIsEnabled2;

function foo2() {
 _emscripten_glIsEnabled2 = function _glIsEnabled2(cap) {};
 _emscripten_glIsEnabled2();
}

Module.foo2 = foo2;
