function getAuthErrorMessage(error) {
  return error?.message || '数据连接失败，请稍后重试'
}

function showPageAuthFailure(page, error, extraState = {}) {
  if (!page || page._isActive === false) return
  page.setData({
    ...extraState,
    loading: false,
    authError: getAuthErrorMessage(error)
  })
}

function loadPageAfterAuthentication(page, loader, options = {}) {
  const { failureState = {} } = options
  const app = getApp()

  return app.whenAuthenticated()
    .then(() => {
      if (page._isActive === false) return null
      page.setData({ authError: '' })
      return loader()
    })
    .catch(error => {
      showPageAuthFailure(page, error, failureState)
      return null
    })
}

function retryPageAuthentication(page, loader, options = {}) {
  const { loadingState = {}, failureState = {} } = options
  if (page._isActive === false) return Promise.resolve(null)
  page.setData({ ...loadingState, loading: true, authError: '' })

  return getApp().retryAuthentication()
    .then(() => {
      if (page._isActive === false) return null
      return loader()
    })
    .catch(error => {
      showPageAuthFailure(page, error, failureState)
      return null
    })
}

module.exports = {
  showPageAuthFailure,
  loadPageAfterAuthentication,
  retryPageAuthentication
}
