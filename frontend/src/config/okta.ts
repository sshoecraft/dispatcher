export default {
  oidc: {
    clientId: '',
    issuer: '',
    redirectUri: window.location.origin + '/login/callback',
    scopes: ['openid', 'profile', 'email', 'offline_access'],
  },
}
