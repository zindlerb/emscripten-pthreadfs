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
    this.exports = function instantiate(t) {
        function r(u) {
            u.set = function(v, w) {
                this[v] = w;
            };
            u.get = function(v) {
                return this[v];
            };
            return u;
        }
        function s(x) {
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
            var k = x.abort;
            var l = NaN;
            var m = Infinity;
            var n = x.a;
            function q(a, b) {
                a = a | 0;
                b = b | 0;
                n(1024);
                return 0;
            }
            function p() {}
            var o = r([]);
            return {
                b: o,
                c: p,
                d: q
            };
        }
        return s(t);
    }(h);
}).exports;

k = m.d;

f.set(new Uint8Array(b.mem), 1024);

m.c();

k();