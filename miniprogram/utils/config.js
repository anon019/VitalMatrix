/**
 * 应用配置
 */

// 公开仓库默认占位地址，请按你的部署域名修改
const DEFAULT_API_BASE_URL = 'https://your-domain.example.com'

// 如果服务端配置了 WEB_ACCESS_PASSWORD，可在本地填写同一密码
// 不要把真实密码提交到仓库
const SIMPLE_LOGIN_PASSWORD = ''

// API基础地址
const getApiBaseUrl = () => {
  try {
    const accountInfo = wx.getAccountInfoSync()
    const envVersion = accountInfo.miniProgram.envVersion

    if (envVersion === 'develop') {
      return DEFAULT_API_BASE_URL
    } else if (envVersion === 'trial') {
      return DEFAULT_API_BASE_URL
    } else {
      return DEFAULT_API_BASE_URL
    }
  } catch (error) {
    return DEFAULT_API_BASE_URL
  }
}

module.exports = {
  // API基础地址
  API_BASE_URL: getApiBaseUrl(),

  // 简易登录密码（可选）
  SIMPLE_LOGIN_PASSWORD,

  // API超时时间（毫秒）
  REQUEST_TIMEOUT: 10000,

  // Token存储key
  TOKEN_KEY: 'token',
  USER_INFO_KEY: 'userInfo',

  // 应用信息
  APP_NAME: 'Health Assistant',
  APP_VERSION: '0.2.1'
}
