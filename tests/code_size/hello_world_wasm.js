var c = Module;

var d = new TextDecoder("utf8");

function e(a) {
    if (!a) return "";
    for (var k = a + NaN, b = a; !(b >= k) && f[b]; ) ++b;
    return d.decode(f.subarray(a, b));
}

var f, g, h;

WebAssembly.instantiate(c.wasm, {
    a: {
        a: function(a) {
            console.log(e(a));
        }
    }
}).then((function(a) {
    a = a.instance.exports;
    h = a.e;
    g = a.b;
    f = new Uint8Array(g.buffer);
    a.d();
    h();
}));