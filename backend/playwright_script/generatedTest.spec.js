import { test, expect } from '@playwright/test';

            test('Generated Test', async ({ page }) => {

                // 2026-02-16 19:29:48 click
    await page.click('xpath=//input[@id='username']');
    // 2026-02-16 19:29:52 fill
    await page.fill('xpath=//input[@id='username']', 'mdsohail@ivp.in');
    // 2026-02-16 19:30:02 click
    await page.click('xpath=//input[@id='client-dropdown']');
    // 2026-02-16 19:30:10 click
    await page.click('xpath=//div[@id='section-client']//div[normalize-space(.)='pmqaautomationuat']');
    // 2026-02-16 19:30:15 click
    await page.click('xpath=//input[@id='submit-button']');
    // 2026-02-16 19:30:19 click
    await page.click('xpath=//input[@id='password']');
    // 2026-02-16 19:30:23 fill
    await page.fill('xpath=//input[@id='password']', 'ivp@123');
    // 2026-02-16 19:30:27 click
    await page.click('xpath=//input[@id='submit-button']');
    // 2026-02-16 19:30:43 click
    await page.click('xpath=//div[@data-testid='pm_date_calendar']//button[.//*[@data-testid='CalendarMonthIcon']]');
    // 2026-02-16 19:30:50 click
    await page.click('xpath=//button[@aria-label='calendar view is open, switch to year view']');
    // 2026-02-16 19:30:58 click
    await page.click('xpath=//div[@role='dialog']//button[@role='radio' and normalize-space(.)='2025']');
    // 2026-02-16 19:31:05 click
    await page.click('xpath=//div[@role='radiogroup']//button[@role='radio' and normalize-space(@aria-label)='February']');
    // 2026-02-16 19:31:18 click
    await page.click('xpath=//div[@role='dialog']//div[@role='grid']//button[normalize-space(.)='28' and not(contains(@class,'dayOutsideMonth'))]');
    // 2026-02-16 19:31:36 click
    await page.click('xpath=//div[@data-testid='user-details']//p[@aria-label='pmqaautomationuat']');
    // 2026-02-16 19:31:42 click
    await page.click('xpath=//div[@data-testid='userCard']//button[@title='Sign out']');

            });