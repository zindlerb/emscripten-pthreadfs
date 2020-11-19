var b = Module;

var d = new TextDecoder("utf8");

function e(a) {
    if (!a) return "";
    for (var l = a + NaN, c = a; !(c >= l) && f[c]; ) ++c;
    return d.decode(f.subarray(a, c));
}

var f, g;

g = new function(a) {
    this.buffer = new ArrayBuffer(65536 * a.initial);
}({
    initial: 256,
    maximum: 256
});

f = new Uint8Array(g.buffer);

var h = {
    a: function(a) {
        console.log(e(a));
    },
    memory: g
}, k, m = (new function() {
    this.exports = function instantiate(x) {
        function v(y) {
            y.set = function(z, A) {
                this[z] = A;
            };
            y.get = function(z) {
                return this[z];
            };
            return y;
        }
        function w(B) {
            var a = Math.imul;
            var b = Math.fround;
            var c = Math.abs;
            var d = Math.clz32;
            var e = Math.min;
            var f = Math.max;
            var g = Math.floor;
            var h = Math.ceil;
            var i = Math.trunc;
            var j = Math.sqrt;
            var k = B.abort;
            var l = NaN;
            var m = Infinity;
            var n = B.a;
            var o = 5243920;
            function u(a, b) {
                a = a | 0;
                b = b | 0;
                n(1024);
                return 0;
            }
            function r(a) {
                a = a | 0;
                a = o - a & -16;
                o = a;
                return a | 0;
            }
            function t() {
                return o | 0;
            }
            function s(a) {
                a = a | 0;
                o = a;
            }
            function q() {}
            var p = v([]);
            return {
                b: p,
                c: q,
                d: u,
                e: t,
                f: s,
                g: r
            };
        }
        return w(x);
    }(h);
}).exports;

k = m.d;

f.set(new Uint8Array(b.mem), 1024);

m.c();

k();