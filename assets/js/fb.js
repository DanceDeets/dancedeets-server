var jQuery = require('jquery');
require('jquery.cookie');

var FBSetup = function(window, fbPermissions, fbAppId, baseHostname) {
  function deleteLoginCookies() {
    var cookieOptions = {
      domain: '.' + baseHostname,
      path: '/',
    };
    jQuery.removeCookie('fbsr_' + fbAppId, cookieOptions);
    jQuery.removeCookie('user_login_' + fbAppId, cookieOptions);
  }

  function reloadWithNewToken() {
    if (String(window.location).indexOf('?') === -1) {
      window.location += '?nt=1';
    } else {
      window.location += '&nt=1';
    }
  }
  function currentUser() {
    var userLogin = jQuery.cookie('user_login_' + fbAppId);
    if (userLogin) {
      return JSON.parse(userLogin).uid;
    }
  }

  function handleStatusChange(response) {
    if (response.status === 'connected') {
      if (response.authResponse.userID !== currentUser()) {
        // reload through endpoint to set up new user cookie serverside
        // TODO(lambert): Add a full-screen overlay explaining what we are doing...
        reloadWithNewToken();
      }
    } else if (response.status === 'not_authorized') {
      if (currentUser()) {
        // the user is logged in to Facebook, but not connected to the app
        deleteLoginCookies();
        // TODO(lambert): Add a full-screen overlay explaining what we are doing...
        reloadWithNewToken('not_authorized');
      }
    } else {
      // the user isn't even logged in to Facebook.
    }
  }

  function initFBCode(FB) {
    function login() {
      FB.login(function(/* response */) {}, {
        scope: fbPermissions,
      });
    }

    function logout() {
      // Seems the logout callback isn't being called, so ensure we delete the cookie here
      deleteLoginCookies();
      FB.getLoginStatus(function(response) {
        if (response.status === 'connected') {
          FB.logout(function(/* response */) {
            window.location.reload();
          });
        } else {
          window.location.reload();
        }
      });
    }

    FB.init({version: 'v2.0', appId: fbAppId, status: true, cookie: true, xfbml: true});
    FB.Event.subscribe('auth.statusChange', handleStatusChange);

    jQuery('.click-login').on('click', login);
    jQuery('.click-logout').on('click', logout);
  }

  window.fbAsyncInit = function() {
    initFBCode(window.FB);
  };

  // Facebook/Login Code
  (function(d, s, id) {
    var js;
    var fjs = d.getElementsByTagName(s)[0];
    if (d.getElementById(id)) {
      return;
    }
    js = d.createElement(s); js.id = id;
    js.src = '//connect.facebook.net/en_US/sdk.js';
    fjs.parentNode.insertBefore(js, fjs);
  })(document, 'script', 'facebook-jssdk');
};

module.exports = FBSetup;

