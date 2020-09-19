/**
 * @license
 * Copyright 2020 The Emscripten Authors
 * SPDX-License-Identifier: MIT
 */

// Enough "polyfill" to support readSync().
XMLHttpRequest = function() {
  this.open = function(method, url, async) {
    assert(method == 'GET');
    assert(!async);
    this.url = url;
  };
  this.send = function() {
    var fs = require('fs');
    var path = require('path');
    var url = path['normalize'](this.url);
    var binary = this.responseType === 'arraybuffer';
    this.responseText = fs['readFileSync'](url, binary ? null : 'utf8');
  };
};
