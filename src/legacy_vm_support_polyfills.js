if (typeof Promise === 'undefined') {
  // Minimal Promise polyfill, enough for emscripten's simple internal usage.
  Promise = function(func) {
    var then; // FIXME stackify!
    var that = this;
    this.then = function(then_) {
      then = then_;
      return that;
    };
    setTimeout(function() {
      func(function promise_resolve() {
        if (then) {
          return then.apply(null, arguments);
        }
      }, abort);
    }, 0);
    return this;
  };
}

