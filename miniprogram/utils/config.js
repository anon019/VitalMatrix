/**
 * 应用配置
 *
 * 重要：请将下面的 API_BASE_URL 替换为您自己的服务器域名
 */

// TODO: 替换为您的服务器域名
const API_DOMAIN = 'https://your-domain.com'

// API基础地址
// 根据环境自动切换（开发环境使用本地，生产环境使用域名）
const getApiBaseUrl = () => {
  // 获取当前账号信息
  const accountInfo = wx.getAccountInfoSync()
  const envVersion = accountInfo.miniProgram.envVersion

  if (envVersion === 'develop') {
    // 开发版：使用远程服务器（本地调试时也可改为 http://localhost:8000）
    return API_DOMAIN
  } else if (envVersion === 'trial') {
    // 体验版：使用测试服务器
    return API_DOMAIN
  } else {
    // 正式版：使用生产服务器
    return API_DOMAIN
  }
}

module.exports = {
  // API基础地址
  API_BASE_URL: getApiBaseUrl(),

  // API超时时间（毫秒）
  REQUEST_TIMEOUT: 10000,

  // Token存储key
  TOKEN_KEY: 'token',
  USER_INFO_KEY: 'userInfo',

  // 应用信息
  APP_NAME: 'Health Assistant',
  APP_VERSION: '0.2.0'
}
