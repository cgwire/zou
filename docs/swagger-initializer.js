window.onload = function() {
  //<editor-fold desc="Changeable Configuration Block">
  const CaseInsensitiveFilterPlugin = function (system) {
    return {
        fn: {
            opsFilter: (taggedOps, phrase) => {
                return taggedOps.filter((tagObj, tag) => tag.toLowerCase().indexOf(phrase.toLowerCase()) !== -1);
            }
        }
    }
  };
  // the following lines will be replaced by docker/configurator, when it runs in a docker-container
  window.ui = SwaggerUIBundle({
    
    url: window.location.protocol + '//' + window.location.host + '/openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    filter: true,
    docExpansion: 'list',
    presets: [
      SwaggerUIBundle.presets.apis,
      SwaggerUIStandalonePreset
    ],
    plugins: [
      SwaggerUIBundle.plugins.DownloadUrl,
      CaseInsensitiveFilterPlugin
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
