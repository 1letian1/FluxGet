import { expect, test } from '@playwright/test'

const viewports = [
  { width: 1024, height: 768 },
  { width: 1124, height: 1068 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
]

for (const viewport of viewports) {
  test(`workspace visual layout at ${viewport.width}x${viewport.height}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport)
    await page.goto('/')
    await expect(page.getByRole('heading', { name: '新建下载任务' })).toBeVisible()
    await expect(page.getByRole('navigation', { name: '主导航' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '下载队列' })).toBeVisible()

    const layout = await page.evaluate(() => ({
      width: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
    }))
    expect(layout.scrollWidth).toBeLessThanOrEqual(layout.width)
    expect(layout.bodyScrollWidth).toBeLessThanOrEqual(layout.width)
    await page.screenshot({ path: testInfo.outputPath(`workspace-${viewport.width}x${viewport.height}.png`), fullPage: true })
  })
}

test('rule preview dialog shows rendered and invalid rows', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('tab', { name: '规则拼接' }).click()
  await page.getByLabel('基础网址').fill('https://plugins.example.test')
  await page.getByLabel('插件名 + 版本（支持从表格粘贴）').fill('sample 1.2\ninvalid')
  await page.getByRole('button', { name: '预览 URL' }).click()

  const dialog = page.getByRole('dialog', { name: 'URL 预览' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('https://plugins.example.test/sample/1.2/sample.hpi')).toBeVisible()
  await expect(dialog.getByText('无效输入')).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('rule-preview.png'), fullPage: true })
})

test('settings and navigation remain usable at tablet width', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 })
  await page.goto('/')
  await page.getByRole('navigation', { name: '配置导航' }).getByRole('button', { name: '偏好设置' }).click()
  await expect(page.getByRole('heading', { name: '偏好设置' })).toBeVisible()
  await page.getByPlaceholder('例如 plugins').fill('browser-tests')
  await expect(page.getByRole('button', { name: '保存设置' })).toBeEnabled()
  await page.screenshot({ path: test.info().outputPath('settings-tablet.png'), fullPage: true })
})

test('direct task downloads through the API and appears in history', async ({ page }, testInfo) => {
  const downloadProbe = await page.request.get('http://127.0.0.1:8766/test-download')
  expect(downloadProbe.status()).toBe(200)
  const settingsResponse = await page.request.get('http://127.0.0.1:8766/api/v1/settings')
  expect(settingsResponse.ok()).toBeTruthy()
  const settings = await settingsResponse.json()
  delete settings.updated_at
  const outputDir = testInfo.outputPath('downloads')
  const updated = await page.request.put('http://127.0.0.1:8766/api/v1/settings', {
    data: { ...settings, output_dir: outputDir },
  })
  expect(updated.ok()).toBeTruthy()

  await page.goto('/')
  await page.getByLabel('下载链接（每行一个 HTTP/HTTPS URL）').fill('http://127.0.0.1:8766/test-download')
  await page.getByRole('button', { name: '加入下载队列' }).click()
  await expect(page.getByRole('status')).toContainText('已加入 1 个任务', { timeout: 10_000 })
  await expect(page.getByText('test-download', { exact: true })).toBeVisible()
  await expect.poll(async () => {
    const response = await page.request.get('http://127.0.0.1:8766/api/v1/tasks/history')
    const tasks = (await response.json()).items as Array<{ filename: string; status: string }>
    return tasks.find((task) => task.filename === 'test-download')?.status
  }, { timeout: 10_000 }).toBe('completed')

  await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: '下载历史' }).click()
  await expect(page.getByText('test-download', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('completed-history.png'), fullPage: true })
})
