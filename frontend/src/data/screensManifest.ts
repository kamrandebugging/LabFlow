export interface ScreenMeta {
  id: number;
  title: string;
  route: string;
  htmlFile: string;
  pngFile: string;
  batch: number;
  batchName: string;
}

export const ALL_SCREENS: ScreenMeta[] = [
  {
    "id": 1,
    "title": "Staff Login - City Diagnostic Lab",
    "route": "/login",
    "htmlFile": "01-staff-login.html",
    "pngFile": "01-staff-login.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 2,
    "title": "Two-Factor Authentication - City Diagnostic Lab",
    "route": "/login (step 2, TOTP)",
    "htmlFile": "02-two-factor-auth.html",
    "pngFile": "02-two-factor-auth.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 3,
    "title": "Owner Home Dashboard - LabFlow",
    "route": "/ (Owner)",
    "htmlFile": "03-owner-dashboard.html",
    "pngFile": "03-owner-dashboard.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 4,
    "title": "Manager Home Dashboard - LabFlow",
    "route": "/ (Manager)",
    "htmlFile": "04-manager-dashboard.html",
    "pngFile": "04-manager-dashboard.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 5,
    "title": "Receptionist Home Dashboard - LabFlow",
    "route": "/ (Receptionist)",
    "htmlFile": "05-receptionist-dashboard.html",
    "pngFile": "05-receptionist-dashboard.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 6,
    "title": "Technician Home Dashboard - LabFlow",
    "route": "/ (Technician)",
    "htmlFile": "06-technician-dashboard.html",
    "pngFile": "06-technician-dashboard.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 7,
    "title": "Pathologist Home Dashboard - LabFlow",
    "route": "/ (Pathologist)",
    "htmlFile": "07-pathologist-dashboard.html",
    "pngFile": "07-pathologist-dashboard.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 8,
    "title": "Patient List - LabFlow",
    "route": "/patients",
    "htmlFile": "08-patient-list.html",
    "pngFile": "08-patient-list.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 9,
    "title": "Register Patient - LabFlow",
    "route": "/patients/new",
    "htmlFile": "09-register-patient.html",
    "pngFile": "09-register-patient.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 10,
    "title": "Patient Details - Muhammad Imran - LabFlow",
    "route": "/patients/:id",
    "htmlFile": "10-patient-details.html",
    "pngFile": "10-patient-details.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 11,
    "title": "Patient Edit - LabFlow",
    "route": "/patients/:id/edit",
    "htmlFile": "11-patient-edit.html",
    "pngFile": "11-patient-edit.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 12,
    "title": "Patient History - Muhammad Imran - LabFlow",
    "route": "/patients/:id/history",
    "htmlFile": "12-patient-history.html",
    "pngFile": "12-patient-history.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 13,
    "title": "Invoices - LabFlow",
    "route": "/invoices",
    "htmlFile": "13-invoices.html",
    "pngFile": "13-invoices.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 14,
    "title": "New Invoice - LabFlow",
    "route": "/invoices/new",
    "htmlFile": "14-new-invoice.html",
    "pngFile": "14-new-invoice.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 15,
    "title": "Invoice Detail - INV-2026-0891 - LabFlow",
    "route": "/invoices/:id",
    "htmlFile": "15-invoice-detail.html",
    "pngFile": "15-invoice-detail.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 16,
    "title": "Samples - LabFlow",
    "route": "/samples",
    "htmlFile": "16-samples.html",
    "pngFile": "16-samples.png",
    "batch": 1,
    "batchName": "Batch 1: Auth, Dashboards, Patients, Invoices"
  },
  {
    "id": 17,
    "title": "Collect Sample - LabFlow",
    "route": "/samples/new (step 1)",
    "htmlFile": "17-collect-sample-step1.html",
    "pngFile": "17-collect-sample-step1.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 18,
    "title": "Collect Sample - Step 2 Tests & Collection - LabFlow",
    "route": "/samples/new (step 2)",
    "htmlFile": "18-collect-sample-step2.html",
    "pngFile": "18-collect-sample-step2.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 19,
    "title": "Sample Detail - CDL20261020000041 - LabFlow",
    "route": "/samples/:id",
    "htmlFile": "19-sample-detail.html",
    "pngFile": "19-sample-detail.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 20,
    "title": "Sample Label - CDL20261020000041 - LabFlow",
    "route": "/samples/:id/label",
    "htmlFile": "20-sample-label.html",
    "pngFile": "20-sample-label.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 21,
    "title": "Worklist - City Diagnostic Lab",
    "route": "/worklist",
    "htmlFile": "21-worklist.html",
    "pngFile": "21-worklist.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 22,
    "title": "Result Entry - CDL20261020000041 - LabFlow",
    "route": "/results/entry/:sampleId",
    "htmlFile": "22-result-entry.html",
    "pngFile": "22-result-entry.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 23,
    "title": "Approvals Queue - City Diagnostic Lab",
    "route": "/results/approvals",
    "htmlFile": "23-approvals-queue.html",
    "pngFile": "23-approvals-queue.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 24,
    "title": "Result Detail - Potassium (K+) - CDL20261020000041 - LabFlow",
    "route": "/results/:id",
    "htmlFile": "24-result-detail.html",
    "pngFile": "24-result-detail.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 25,
    "title": "Amend Result - Potassium (K+) - LabFlow",
    "route": "/results/:id/amend",
    "htmlFile": "25-amend-result.html",
    "pngFile": "25-amend-result.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 26,
    "title": "Reports - LabFlow",
    "route": "/reports",
    "htmlFile": "26-reports.html",
    "pngFile": "26-reports.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 27,
    "title": "Report Detail - RPT-2026-01432 - LabFlow",
    "route": "/reports/:id",
    "htmlFile": "27-report-detail.html",
    "pngFile": "27-report-detail.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 28,
    "title": "Patient Report Access - City Diagnostic Lab",
    "route": "/report-access/:token",
    "htmlFile": "28-patient-report-access.html",
    "pngFile": "28-patient-report-access.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 29,
    "title": "Link Expired - City Diagnostic Lab",
    "route": "/link-expired",
    "htmlFile": "29-link-expired.html",
    "pngFile": "29-link-expired.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 30,
    "title": "Exceptions - LabFlow",
    "route": "/exceptions",
    "htmlFile": "30-exceptions.html",
    "pngFile": "30-exceptions.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 31,
    "title": "Test Catalog - LabFlow",
    "route": "/settings/tests",
    "htmlFile": "31-test-catalog.html",
    "pngFile": "31-test-catalog.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 32,
    "title": "Test Panels - LabFlow",
    "route": "/settings/panels",
    "htmlFile": "32-test-panels.html",
    "pngFile": "32-test-panels.png",
    "batch": 2,
    "batchName": "Batch 2: Samples, Worklist, Results, Reports"
  },
  {
    "id": 33,
    "title": "Branches - City Diagnostic Lab",
    "route": "/settings/branches",
    "htmlFile": "33-branches.html",
    "pngFile": "33-branches.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 34,
    "title": "Tenant Settings - LabFlow",
    "route": "/settings/tenant",
    "htmlFile": "34-tenant-settings.html",
    "pngFile": "34-tenant-settings.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 35,
    "title": "Data Export - LabFlow",
    "route": "/settings/exports",
    "htmlFile": "35-data-export.html",
    "pngFile": "35-data-export.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 36,
    "title": "Referral Partners - LabFlow",
    "route": "/partners",
    "htmlFile": "36-referral-partners.html",
    "pngFile": "36-referral-partners.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 37,
    "title": "Partner Detail - Dr. Farhan Qureshi - LabFlow",
    "route": "/partners/:id",
    "htmlFile": "37-partner-detail.html",
    "pngFile": "37-partner-detail.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 38,
    "title": "Partner Rules - LabFlow",
    "route": "/partners/:id/rules",
    "htmlFile": "38-partner-rules.html",
    "pngFile": "38-partner-rules.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 39,
    "title": "Revenue Share Ledger - LabFlow",
    "route": "/partners/ledger",
    "htmlFile": "39-revenue-share-ledger.html",
    "pngFile": "39-revenue-share-ledger.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 40,
    "title": "Partner Dashboard - Dr. Farhan Qureshi - LabFlow",
    "route": "/partners/:id/dashboard",
    "htmlFile": "40-partner-dashboard.html",
    "pngFile": "40-partner-dashboard.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 41,
    "title": "Settlements - LabFlow",
    "route": "/settlements",
    "htmlFile": "41-settlements.html",
    "pngFile": "41-settlements.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 42,
    "title": "Settlement Detail - Dr. Farhan Qureshi - LabFlow",
    "route": "/settlements/:id",
    "htmlFile": "42-settlement-detail.html",
    "pngFile": "42-settlement-detail.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  },
  {
    "id": 43,
    "title": "Platform Tenants - Super Admin - LabFlow",
    "route": "/platform/tenants",
    "htmlFile": "43-platform-tenants.html",
    "pngFile": "43-platform-tenants.png",
    "batch": 3,
    "batchName": "Batch 3: Settings, Partners, Platform"
  }
];
