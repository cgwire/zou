window.onload = function() {
  //<editor-fold desc="Changeable Configuration Block">

  // the following lines will be replaced by docker/configurator, when it runs in a docker-container
  window.ui = SwaggerUIBundle({
    url: window.location.protocol + '//' + window.location.host + '/openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    presets: [
      SwaggerUIBundle.presets.apis,
      SwaggerUIStandalonePreset
    ],
    plugins: [
      SwaggerUIBundle.plugins.DownloadUrl
    ],
    layout: "StandaloneLayout"
  });

  topbar = document.getElementsByClassName('topbar-wrapper')[0]
  topbar.getElementsByTagName('img')[0].src = "kitsu.svg";
  
  var div = document.createElement("div");
  div.setAttribute('class', 'kitsu-title');
  div.innerHTML = "Kitsu API Documentation";

  topbar.getElementsByClassName("link")[0].appendChild(div);
  //</editor-fold>
};
