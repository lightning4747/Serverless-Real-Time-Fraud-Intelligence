# Sentinel AML Dashboard

A professional React-based dashboard for the Sentinel Anti-Money Laundering (AML) monitoring system. This interface provides comprehensive tools for compliance officers to monitor suspicious activities, manage investigations, and generate regulatory reports.

## Features

### 🎯 Core Functionality
- **Real-time AML Monitoring**: Live dashboard with key performance indicators
- **Alert Management**: Comprehensive alert triage and investigation workflow
- **Transaction Analysis**: Interactive graph visualization of transaction networks
- **Case Management**: Structured investigation workflow with timeline tracking
- **SAR Reporting**: Suspicious Activity Report generation and management
- **Analytics & Insights**: Performance metrics and trend analysis

### 🔒 Compliance Features
- **Regulatory Compliance**: BSA, AML, KYC, and CTR requirements support
- **Risk Scoring**: GNN-based risk assessment with explainable AI
- **Audit Trail**: Complete investigation and decision logging
- **Data Privacy**: PII masking and secure data handling

### 🎨 Professional UI/UX
- **Modern Design**: Clean, professional interface suitable for financial compliance
- **Responsive Layout**: Optimized for desktop and tablet use
- **Interactive Visualizations**: D3.js-powered transaction network graphs
- **Real-time Updates**: Live data streaming and notifications

## Technology Stack

- **Frontend**: React 18 with Material-UI (MUI)
- **Visualization**: Recharts for charts, D3.js for network graphs
- **Routing**: React Router v6
- **Styling**: Material-UI theming with custom financial compliance design
- **Icons**: Material-UI Icons with AML-specific iconography

## Quick Start

### Prerequisites
- Node.js 16+ and npm
- Modern web browser (Chrome, Firefox, Safari, Edge)

### Installation

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

The application will open at `http://localhost:3000`

### Build for Production

```bash
# Create production build
npm run build

# The build folder contains the production-ready files
```

## Project Structure

```
frontend/
├── public/
│   └── index.html          # HTML template
├── src/
│   ├── components/         # Reusable UI components
│   │   ├── Navbar.js      # Top navigation bar
│   │   ├── Sidebar.js     # Side navigation menu
│   │   ├── AlertSummaryChart.js
│   │   ├── RiskScoreDistribution.js
│   │   ├── RecentAlerts.js
│   │   ├── TransactionVolume.js
│   │   └── TransactionGraph.js  # D3.js network visualization
│   ├── pages/             # Main application pages
│   │   ├── Dashboard.js   # Main dashboard with KPIs
│   │   ├── Alerts.js      # Alert management interface
│   │   ├── Investigations.js  # Case management workflow
│   │   ├── Reports.js     # SAR report management
│   │   └── Analytics.js   # Performance analytics
│   ├── App.js            # Main application component
│   └── index.js          # Application entry point
├── package.json          # Dependencies and scripts
└── README.md            # This file
```

## Key Components

### Dashboard
- Real-time KPI monitoring
- Alert trend visualization
- Risk score distribution
- Recent high-priority alerts

### Alert Management
- Comprehensive alert table with filtering
- Risk-based prioritization
- Investigation assignment workflow
- Bulk operations support

### Investigation Workflow
- Structured case management
- Timeline tracking
- Transaction network analysis
- Evidence documentation

### SAR Reporting
- Automated report generation
- FinCEN compliance formatting
- Review and approval workflow
- Export capabilities

### Analytics
- Performance trend analysis
- Model effectiveness metrics
- Operational efficiency tracking
- Compliance reporting

## Demo Features

This interface is designed for demonstration purposes and includes:

- **Mock Data**: Realistic AML scenarios and transaction patterns
- **Interactive Elements**: Fully functional UI components
- **Professional Styling**: Financial compliance industry standards
- **Responsive Design**: Optimized for demo presentations

## AML Domain Integration

The interface incorporates key AML concepts:

- **Risk Categories**: Structuring, layering, integration, smurfing
- **Regulatory Requirements**: BSA, AML, KYC compliance
- **Investigation Workflow**: Standard AML investigation procedures
- **Reporting Standards**: FinCEN SAR format compliance

## Customization

The dashboard can be customized for different financial institutions:

- **Branding**: Logo, colors, and styling
- **Workflows**: Investigation and approval processes
- **Metrics**: Institution-specific KPIs
- **Integrations**: Backend API connections

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## License

This project is part of the Sentinel AML system and follows the project's licensing terms.