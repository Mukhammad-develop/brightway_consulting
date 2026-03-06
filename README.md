# Brightway Consulting

A comprehensive Django-based consulting business management platform with AI-powered Telegram bot integration, designed for tax and immigration consulting services in the UK.

## 🌟 Features

### Public Website
- 🌙 Stunning dark-themed modern design
- 🌐 Multi-language support (English, Russian, Uzbek)
- 📱 Fully responsive for all devices
- ⚡ Smooth animations and interactions

### Admin Panel
- 🔐 Secure authentication system
- 📊 Dashboard with key metrics and AI usage statistics
- 👥 Comprehensive user and case management
- 📝 AI-powered report generation with business insights
- 🔧 Dynamic service configuration

### AI Features
- 🤖 GPT-4o-mini powered chat assistant for consultations
- 🎤 Whisper-1 voice transcription with multi-language support
- 📊 Automatic profile extraction from conversations
- 🧠 Intelligent service detection from user messages
- 📈 AI-driven business report conclusions

### Telegram Integration
- 🤖 AI-powered chatbot for client consultations
- 📄 Document upload and processing
- 🎤 Voice message transcription and processing
- 💬 Multi-language AI responses (EN/RU/UZ)

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- pip (Python package manager)
- ffmpeg (for voice message conversion)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/brightway-consulting.git
   cd brightway-consulting
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install ffmpeg (for voice transcription)**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install ffmpeg
   
   # macOS
   brew install ffmpeg
   
   # Windows - download from https://ffmpeg.org/download.html
   ```

5. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your settings (see Environment Variables section)
   ```

6. **Run migrations**
   ```bash
   python manage.py migrate
   ```

7. **Start the development server**
   ```bash
   python manage.py runserver
   ```

8. **Access the application**
   - Public website: http://localhost:8000/
   - Admin panel: http://localhost:8000/admin/login

### Default Admin Credentials
- Username: `admin` (or as configured in .env)
- Password: `admin123` (or as configured in .env)

## 🤖 AI Configuration

### OpenAI Setup

1. **Get API Key**: Sign up at [OpenAI](https://platform.openai.com/) and create an API key

2. **Configure in .env**:
   ```env
   OPENAI_API_KEY=sk-your-api-key-here
   ```

3. **Models Used**:
   - **GPT-4o-mini**: For chat responses, service detection, profile extraction, and report conclusions
   - **Whisper-1**: For voice message transcription

### AI Features

#### Chat Assistant
- Intelligent responses using GPT-4o-mini
- Service-specific system prompts configurable in admin panel
- Context-aware conversations with history
- Automatic language detection and response

#### Voice Transcription
- Automatic transcription of voice messages
- Supports multiple languages (auto-detected or user language preference)
- Converts Telegram's OGG format to WAV using ffmpeg
- Transcription stored in database for search

#### Profile Extraction
- Automatically extracts user information from conversations
- Fields: name, nationality, phone, email, service interest, etc.
- Triggered periodically (every 10 messages)
- Results stored in UserAiProfile model

#### Service Detection
- Keyword-based detection (fast)
- AI-enhanced detection for unclear messages (GPT-4o-mini)
- Configurable keywords per service in admin panel

#### Report Conclusions
- AI-generated business insights for reports
- Analyzes key metrics and trends
- Provides actionable recommendations

### AI Usage Monitoring

The dashboard displays AI usage statistics:
- API calls today
- Tokens used
- Average response time
- Error rate
- Transcriptions count

### Testing AI Prompts

In the Service Management page, you can test AI prompts:
1. Go to Admin Panel → Services
2. Edit a service
3. Click "Test Prompt" button
4. Enter a sample user message
5. See AI response in real-time

### AI Error Handling

- Automatic retry with exponential backoff
- Graceful fallback responses when AI is unavailable
- Rate limiting to prevent API abuse
- All errors logged to `bot.log`

## 📁 Project Structure

```
bwc/                    # Django project settings
    settings.py
    urls.py
    wsgi.py

bot/                    # Telegram bot
    bot.py              # Main bot logic (pyTelegramBotAPI)
    userbot.py          # Userbot for chat import (Telethon)
    services.py         # AI services (GPT, Whisper, profile extraction)
    messages.py         # Multi-language translations

core/                   # Core models
    models.py           # All database models
    migrations/
    management/
        commands/
            run_bot.py
            run_userbot.py
            seed_data.py

panel/                  # Admin panel app
    urls.py
    decorators.py       # @login_required, @master_required, @elevated_required
    views/
        auth.py         # Login/logout/profile
        dashboard.py    # Dashboard with AI stats
        users.py        # User management + messaging
        cases.py        # Case management
        files.py        # File management
        services.py     # Service management + AI prompt testing
        reports.py      # AI-powered reports
        team.py         # Team management
        notifications.py
        import_chat.py
        helpers.py      # Utility functions

public/                 # Public website app
    urls.py
    views.py

templates/
    public/             # Public website templates
        index.html
        services.html
        contact.html
    panel/              # Admin panel templates
        base.html
        login.html
        dashboard.html
        ... (many more)

static/
    css/
        style.css       # Public website styles
        admin.css       # Admin panel styles
    js/
        main.js         # JavaScript with translations

uploads/                # Media files (user uploads)
sessions/               # Telegram session files
bot.log                 # Bot activity log
```

## 🔧 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DJANGO_SECRET_KEY` | Django secret key | Yes |
| `DEBUG` | Debug mode (True/False) | Yes |
| `ALLOWED_HOSTS` | Comma-separated hosts | Yes |
| `BOT_TOKEN` | Telegram bot token | For bot |
| `OPENAI_API_KEY` | OpenAI API key | For AI features |
| `TG_API_ID` | Telegram API ID | For userbot |
| `TG_API_HASH` | Telegram API hash | For userbot |
| `TG_PHONE` | Phone for userbot 1 | For userbot |
| `TG_PHONE_2` | Phone for userbot 2 (optional) | For userbot |
| `ADMIN_USERNAME` | Master admin username | Yes |
| `ADMIN_PASSWORD` | Master admin password | Yes |
| `MASTER2_USERNAME` | DB master username (default: bwmaster) | No |
| `MASTER2_PASSWORD` | DB master password | No |

## 📝 Database Models

### User & Case Models
- **TgUser**: Telegram user information
- **Case**: Consulting cases with conversation history
- **Document**: Uploaded documents (with transcription field)
- **Payment**: Payment records

### Admin Models
- **AdminUser**: Admin panel users (master/admin/consultant roles)
- **AdminAssignment**: User-consultant assignments
- **Notification**: Admin notifications
- **ClientNote**: Notes about clients

### Service Configuration
- **ServiceDefinition**: Dynamic service configuration with AI prompts
- **ServiceStep**: Service workflow steps
- **CaseTracking**: Case progress tracking
- **CaseTrackingLog**: Step change history

### AI Models
- **UserAiProfile**: Extracted user profile data
- **AiReport**: Generated reports with AI conclusions

## 🌐 Multi-Language Support

The application supports three languages:
- 🇬🇧 English (default)
- 🇷🇺 Russian (Русский)
- 🇺🇿 Uzbek (O'zbek)

AI responses are automatically generated in the user's preferred language.

## 🤖 Telegram Bot

### Starting the Bot

```bash
# Using management command
python manage.py run_bot

# Or using shell script
./bot/start_bot.sh    # Start in background
./bot/stop_bot.sh     # Stop
./bot/status.sh       # Check status
```

### Bot Commands
- `/start` - Welcome message and language selection
- `/help` - Show available commands
- `/language` - Change language preference
- `/mycase` - Check current case status
- `/newcase` - Start a new consultation

### Bot Features
- Multi-language support (EN/RU/UZ)
- AI-powered responses using GPT-4o-mini
- Document/photo/voice message handling
- Automatic voice transcription with Whisper-1
- Service detection from user messages
- Conversation history in database

### Userbot (Chat Import)

```bash
# Authenticate first time
python manage.py run_userbot --auth

# Start userbot
python manage.py run_userbot

# Or using shell scripts
./bot/start_userbot.sh
./bot/stop_userbot.sh
```

## 🛠 Troubleshooting

### AI Features Not Working

1. **Check API Key**: Ensure `OPENAI_API_KEY` is set in `.env`
2. **Check Logs**: View `bot.log` for errors
3. **Test Connectivity**: Try the "Test Prompt" feature in Services

### Voice Transcription Failing

1. **Install ffmpeg**: Required for audio conversion
2. **Check File Permissions**: Ensure uploads folder is writable
3. **Check Audio Format**: Whisper supports mp3, wav, m4a, webm, ogg

### Rate Limiting

The AI services include built-in rate limiting:
- 60 API calls per minute
- Automatic tracking and warning in dashboard

## 🚧 Development Roadmap

### Step 1 ✅
- [x] Project structure
- [x] All database models
- [x] Public website with dark theme
- [x] Basic admin authentication

### Step 2 ✅
- [x] Full admin dashboard with statistics
- [x] Cases management
- [x] User management
- [x] Files management

### Step 3 ✅
- [x] Advanced admin features
- [x] Service management
- [x] Reports generation
- [x] Team management
- [x] Client notes
- [x] Notifications system

### Step 4 ✅
- [x] Telegram bot integration
- [x] AI-powered responses
- [x] Multi-language support
- [x] Document/voice handling
- [x] Chat import functionality
- [x] Admin panel messaging integration

### Step 5 ✅ (Final)
- [x] OpenAI GPT-4o-mini integration
- [x] Whisper-1 voice transcription
- [x] AI profile extraction
- [x] Enhanced service detection
- [x] AI-driven report conclusions
- [x] AI usage statistics dashboard
- [x] Test prompt functionality
- [x] Comprehensive error handling

## 🤝 Contributing

This is a private project for Brightway Consulting. For any questions or issues, please contact the development team.

## 📄 License

Private - All rights reserved.

---

Built with ❤️ using Django, OpenAI, and modern web technologies.
