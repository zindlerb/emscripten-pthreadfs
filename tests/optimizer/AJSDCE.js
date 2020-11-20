
// all unused
var x;
var y = 1;
var z = fleefl();
var xx, yy = 1, zz = fleefl(); // but zz must remain due to the side effects in the value
function f(x, y, z) {
  // shadow the x,y,z
  x = y;
  y = z;
}

// exported
function g(a) {
  return a+1;
}
Module['g'] = g;

// used
function h(a) {
  var t; // unused
  return a+1;
}
print(h(123));

// inner workings
(function() {
  var x;
  var y = 1;
  var z = fleefl();
  var xx, yy = 1, zz = fleefl();
  function f(x, y, z) {
    // shadow the x,y,z
    x = y;
    y = z;
  }

  // exported
  function g(a) {
    return a+1;
  }
  Module['g'] = g;

  // used
  function hh(a) {
    var t; // unused
    return a+1;
  }
  print(hh(123));
})();

function glue() {
  function lookup() { // 2 passes needed for this one
    throw 1;
  }
  function removable() { // first remove this
    lookup();
  }
}
glue();

var buffer = new ArrayBuffer(1024);

// unnecessary leftovers that seem to have side effects
"undefined" !== typeof TextDecoder && new TextDecoder("utf8");
new TextDecoder("utf8");
new Int8Array(buffer);
new Uint8Array(buffer);
new Int16Array(buffer);
new Uint16Array(buffer);
new Int32Array(buffer);
new Uint32Array(buffer);
new Float32Array(buffer);
new Float64Array(buffer);

// for comparison, real side effects
new SomethingUnknownWithSideEffects("utf8");
new TextDecoder(Unknown());

// A write-only value can be removed.
var writeOnly;
var readWrite;

function doWrites(dummy) {
  writeOnly = 10;
  writeOnly = 20;
  readWrite = 30;
  doWrites(readWrite);
  // After removing the write, these have no side effects.
  writeOnly = asm['foo'];
  writeOnly = Module['foo'];
  writeOnly = Module['asm']['foo'];
  // This never had any.
  Math.floor;
  // But other things do have side effects.
  writeOnly = doWrites();
}

Module.doWrites = doWrites;

// Check we properly remove a write whose output is used.

var HEAP16, HEAP32;
function updateGlobalBufferAndViews(buf) {
  // HEAP16 is not needed, but we do need to pass along the effectful value.
  Module['HEAP16'] = HEAP16 = buf();
  // HEAP32 is not needed, but we do need to pass along the effectless value.
  Module['HEAP32'] = HEAP32 = buf;
}
updateGlobalBufferAndViews();
