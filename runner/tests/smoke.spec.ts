import { test, expect } from '@playwright/test';

test('Beautiful E2E 前端工作台加载完成', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Beautiful E2E').first()).toBeVisible();
  await expect(page.getByLabel('项目控制')).toBeVisible();
  await expect(page.getByLabel('自然语言用例生成器')).toBeVisible();
  await expect(page.getByRole('button', { name: '生成' })).toBeVisible();
  await expect(page.getByRole('button', { name: '打开 DSL' })).toBeVisible();
});
