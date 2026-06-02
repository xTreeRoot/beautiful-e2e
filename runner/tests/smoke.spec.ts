import { test, expect } from '@playwright/test';

test('Beautiful E2E 前端工作台加载完成', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Beautiful E2E').first()).toBeVisible();
  await expect(page.getByRole('button', { name: '生成' })).toBeVisible();
  await expect(page.getByText('节点工具箱')).toBeVisible();
  await expect(page.getByText('DSL').first()).toBeVisible();
});
