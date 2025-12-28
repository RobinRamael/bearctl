(import (
  fetchTarball {
    url = "https://github.com/edolstra/flake-compat/archive/master.tar.gz";
    sha256 = "1biy60a6gva1k4phpwhg1c1wdwaalnn2wakrv53a7k6bb3qkna0k";
  }
) {
  src = ./.;
}).shellNix
