import { test, expect } from '@playwright/test'
import { SettingsPage } from '../../pageObjects/settingsPage'

// Entries dated 2026, after every fixture ride, so no ride's FTP changes. They are this
// spec's own (claimed in libs/constants.ts) and removed first if an earlier run left them.
const MARCH = '2026-03-01'
const JUNE = '2026-06-01'
// The year of birth estimates threshold heart rate from age, for rides without power from
// that year on. This year's leaves every fixture ride (2025) without an estimate, so no
// other spec's TSS or fitness changes.
const THIS_YEAR = new Date().getFullYear()
// 90 % of the age-predicted max (208 - 0.7 x age) at age 0.
const ESTIMATE_AT_0 = '187 bpm'

test('saving, replacing and removing athlete values', async ({ page }) => {
  const settings = new SettingsPage(page)

  await test.step("Start without this spec's entries", async () => {
    await settings.goto()
    await expect(settings.today.value('FTP')).toBeVisible()
    for (const date of [MARCH, JUNE]) {
      if (await settings.removeButton(date).count()) await settings.removeEntry(date)
    }
  })

  await test.step('Save FTP, weight (in lb), max and threshold heart rate from March', async () => {
    await settings.saveValues({
      from: MARCH,
      ftp: '250',
      weight: '165',
      maxHr: '188',
      thresholdHr: '165',
    })
    await expect(settings.notice).toHaveText(`Saved values from ${MARCH}.`)
    await expect(settings.entry(MARCH)).toContainText('250 W')
    await expect(settings.entry(MARCH)).toContainText('165.0 lb')
    await expect(settings.entry(MARCH)).toContainText('188 bpm')
    await expect(settings.entry(MARCH)).toContainText('165 bpm')
    await expect(settings.today.value('FTP')).toHaveText('250 W')
    await expect(settings.today.value('Threshold heart rate')).toHaveText('165 bpm')
  })

  await test.step('A new FTP from June; weight carries forward', async () => {
    await settings.saveValues({ from: JUNE, ftp: '260' })
    await expect(settings.today.value('FTP')).toHaveText('260 W')
    await expect(settings.today.value('Weight')).toHaveText('165.0 lb')
  })

  await test.step('Saving June again replaces it', async () => {
    await settings.saveValues({ from: JUNE, ftp: '265' })
    await expect(settings.entry(JUNE)).toHaveCount(1)
    await expect(settings.entry(JUNE)).toContainText('265 W')
  })

  await test.step('In metric, the weight is shown in kg', async () => {
    await settings.metricUnits.click()
    await expect(settings.entry(MARCH)).toContainText('74.8 kg')
    await expect(settings.weight, { message: 'The form should ask for kg too' }).toBeVisible()
    await expect(settings.form.getByText('Weight (kg)')).toBeVisible()
  })

  await test.step('Remove June: March applies again', async () => {
    await settings.removeEntry(JUNE)
    await expect(settings.today.value('FTP')).toHaveText('250 W')
  })

  await test.step('Saving with no values is refused', async () => {
    await settings.saveValues({ from: JUNE })
    await expect(settings.error).toHaveText(
      'Give at least one of FTP, weight, max or threshold heart rate.',
    )
    await expect(settings.entry(JUNE), { message: 'Nothing should be saved' }).toHaveCount(0)
  })
})

test('a year of birth estimates threshold heart rate', async ({ page }) => {
  const settings = new SettingsPage(page)

  await test.step('Start without a year of birth', async () => {
    await settings.goto()
    await settings.setBirthYear('')
    await expect(settings.birthYearNotice).toHaveText('Year of birth cleared.')
  })

  await test.step('Born this year: the estimate is for age 0', async () => {
    await settings.setBirthYear(String(THIS_YEAR))
    await expect(settings.birthYearNotice).toHaveText(
      `Saved: born ${THIS_YEAR}. Estimated threshold heart rate today: ${ESTIMATE_AT_0}.`,
    )
    await expect(settings.birthYear, {
      message: 'The saved year should stay in the field',
    }).toHaveValue(String(THIS_YEAR))
  })

  await test.step('A year before 1900 is refused and the saved one kept', async () => {
    await settings.setBirthYear('1899')
    await expect(settings.birthYearError).toHaveText(
      `Give a year of birth from 1900 to ${THIS_YEAR}.`,
    )
    await page.reload()
    await expect(settings.birthYear).toHaveValue(String(THIS_YEAR))
  })

  await test.step('Clear it again', async () => {
    await settings.setBirthYear('')
    await expect(settings.birthYearNotice).toHaveText('Year of birth cleared.')
  })
})
