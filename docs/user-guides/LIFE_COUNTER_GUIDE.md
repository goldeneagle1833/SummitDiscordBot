# 📱 Mobile Life Counter & Match Reporting Guide

**Sorcerers Summit - 2-Player Life Counter**

A mobile-optimized tool for tracking life totals during Sorcery: Contested Realm games and reporting match results to update your ELO ranking.

---

## 🎯 Quick Start

1. **Access the Life Counter**
   - Visit [sorcererssummit.com/life-counter](https://sorcererssummit.com/life-counter) on your mobile device
   - Or tap the life counter icon in the navbar (mobile only)

2. **Track Your Game**
   - Use the **+** and **−** buttons to adjust life totals
   - Tap threshold element buttons to track your mana
   - State automatically saves (even if you refresh the page!)

3. **Report Your Match** (when game ends)
   - When a player reaches 0 life, the **"📝 Report Match"** button appears
   - Fill in opponent details and deck URL
   - Submit the report for ELO tracking

4. **Confirm Opponent's Reports**
   - If your opponent reports a match, you'll see a notification
   - Review the match details and confirm or deny

---

## 📖 Detailed Instructions

### Part 1: Using the Life Counter

#### **Starting a Game**

When you load the life counter page:
- Both players start at **20 life**
- All threshold counters (Water, Fire, Earth, Air) start at **0**
- Your state is saved to your browser automatically

#### **Adjusting Life Totals**

**For your life** (bottom half of screen):
- Tap **+** to increase life by 1
- Tap **−** to decrease life by 1

**For opponent's life** (top half of screen - rotated 180°):
- Tap their **+** to increase their life by 1
- Tap their **−** to decrease their life by 1

> 💡 **Tip**: Hand your phone to your opponent so they can see their life total right-side-up!

#### **Tracking Threshold (Mana)**

Each player has 4 threshold element counters at their side of the screen:

- 💧 **Water** (blue)
- 🔥 **Fire** (red)
- 🌍 **Earth** (brown)
- 💨 **Air** (light blue)

To adjust threshold counters:
- Tap **+** above an element icon to increase
- Tap **−** below an element icon to decrease

#### **Visual Indicators**

Life totals change color based on your health:
- **White**: Normal (6-29 life)
- **Yellow**: Low (1-5 life)
- **Red "DD"**: Dead (0 life) - triggers match reporting!
- **Green**: High (30+ life)

#### **Fullscreen Mode**

- Tap the **⛶** icon in the top-right to enter fullscreen
- Great for eliminating distractions during your game
- Tap again to exit fullscreen

#### **Resetting the Counter**

- Tap the **↻** icon in the top-right to reset
- Confirms before clearing (prevents accidental resets)
- Starts a fresh game with both players at 20 life

---

### Part 2: Reporting a Match

#### **When Can You Report?**

The **"📝 Report Match"** button appears when:
- Your life reaches 0 (you lost), OR
- Your opponent's life reaches 0 (you won)

#### **Match Report Process**

**Step 1: Click "Report Match"**
- A form appears with your final life totals already filled in

**Step 2: Select Your Opponent**
- Start typing your opponent's name in the search box
- Recent opponents appear first (marked with "Recent" badge)
- Click on their name to select them

**Step 3: Enter Your Deck URL** *(Required)*
- Paste your Curiosa.io deck URL
- Example: `https://curiosa.io/decks/cmlnbvekh01ci04lbaq8zhlyw`
- The system validates this is a real Curiosa URL

**Step 4: Indicate Turn Order** *(Required)*
- Click **"First"** if you went first
- Click **"Second"** if your opponent went first

**Step 5: Submit the Result**
- Click **"I Won"** if you won the match
- Click **"I Lost"** if you lost the match

**Step 6: Wait for Confirmation**
- Your opponent receives a notification
- They have **48 hours** to confirm or deny
- After 48 hours, the match auto-confirms

---

### Part 3: Confirming Match Reports

#### **Receiving Match Confirmations**

When someone reports a match against you:
1. A modal appears automatically showing pending confirmations
2. You'll see:
   - Who reported the match
   - Whether they reported you as winner or loser
   - Final life totals
   - Who went first
   - Their deck URL (if provided)

#### **How to Confirm a Match**

**Step 1: Review the Details**
- Check if the result matches what actually happened
- Verify the final life totals
- Make sure turn order is correct

**Step 2: (Optional) Add Your Deck URL**
- If you didn't provide your deck URL, you can add it now
- Example: `https://curiosa.io/decks/your-deck-id`

**Step 3: Make Your Decision**
- Click **"Confirm"** if the report is accurate
  - ELO ratings update immediately
  - Match is recorded in your history
- Click **"Deny"** if the report is incorrect
  - No ELO change occurs
  - Submitter is notified of the denial

**Step 4: Confirmation Complete**
- Success message appears
- Modal closes automatically after 2 seconds
- Check the leaderboard to see your new ELO!

#### **Checking Pending Confirmations**

The confirmation modal shows a list of all pending reports:
- Tap any pending confirmation to view details
- Click **"← Back to List"** to return to the list
- The page automatically checks for new confirmations every 30 seconds

---

## ⚙️ Features & Settings

### **Session Storage (Auto-Save)**

Your life counter state is automatically saved to your browser:
- Survives page refreshes
- Persists if you close the tab and return
- Only clears when you tap **Reset** or start a new match report

### **Login Requirements**

You can use the life counter **without logging in**, but to report matches you must:
- Log in with **Discord** or **Google**
- Link your Discord account for ELO tracking

### **Match Confirmation Expiration**

- All match reports expire after **48 hours**
- If opponent doesn't respond within 48 hours, match **auto-confirms**
- You'll receive ELO points/losses automatically

### **Haptic Feedback** (Mobile Only)

- Your phone vibrates when you tap life/threshold buttons
- Provides tactile confirmation of button presses
- Only works on devices that support vibration API

---

## 🔍 Frequently Asked Questions

### **Q: Do I need to log in to use the life counter?**
A: No, you can track life without logging in. However, you **must be logged in** to report matches and update ELO.

### **Q: What happens if I refresh the page during a game?**
A: Your life totals and threshold counters are automatically saved and will restore when you return!

### **Q: Can I edit a match report after submitting?**
A: No, but your opponent can **deny** the report if it's incorrect. Then you can submit a new, corrected report.

### **Q: What if my opponent never confirms?**
A: After 48 hours, the match **auto-confirms** and your ELO updates automatically.

### **Q: Can I report matches I didn't track with the life counter?**
A: Yes! You can use the life counter to report **any** match. Just manually set the final life totals before clicking "Report Match", or use the Discord bot's `!record_game` command.

### **Q: Does the life counter work on desktop?**
A: Yes, but it's optimized for mobile. On desktop, you can access it at `/life-counter`, but the layout is designed for vertical mobile screens.

### **Q: What if I accidentally reset the counter mid-game?**
A: You'll need to manually set the life totals back to where they were. There's a confirmation dialog to prevent accidental resets.

### **Q: Can I track more than 2 players?**
A: Not currently. The life counter is designed for standard 1v1 Sorcery games.

### **Q: Is my deck URL required?**
A: **Yes**, the submitter must provide their deck URL. The opponent can optionally add theirs when confirming.

---

## 🛠️ Troubleshooting

### **Life counter doesn't save my changes**

**Solution**: Check if your browser allows session storage:
- Some privacy modes (Incognito, Private Browsing) may block storage
- Try using a regular browser tab
- Clear your browser cache and reload

### **"Report Match" button doesn't appear**

**Checklist**:
- ✅ Is someone at 0 life?
- ✅ Did you refresh the page? (State should restore)
- ✅ Try manually decreasing life to 0 again

### **Opponent search returns no results**

**Possible causes**:
- Opponent hasn't used the bot or website yet (no account)
- Typing error in opponent's name
- Opponent uses a different display name

**Solutions**:
- Ask opponent to log in to sorcererssummit.com first
- Try searching by Discord username instead of display name
- Check for typos or extra characters

### **Match confirmation not appearing**

**Checklist**:
- ✅ Are you logged in with the correct account?
- ✅ Wait 30 seconds for auto-polling to check for new confirmations
- ✅ Refresh the page manually
- ✅ Check if the confirmation expired (48-hour window)

### **Deck URL validation error**

**Valid format**:
```
https://curiosa.io/decks/[deck-id]
```

**Examples**:
- ✅ `https://curiosa.io/decks/cmlnbvekh01ci04lbaq8zhlyw`
- ✅ `https://www.curiosa.io/decks/abc123xyz`
- ✅ `http://curiosa.io/decks/test-deck-123`
- ❌ `curiosa.io/decks/abc123` (missing https://)
- ❌ `https://curiosa.com/decks/abc123` (wrong domain)
- ❌ `https://curiosa.io/deck/abc123` (wrong path - "deck" vs "decks")

---

## 📊 ELO System Integration

### **How ELO Updates Work**

1. **Submit Match Report** → Creates pending confirmation
2. **Opponent Confirms** → Match is recorded
3. **ELO Calculation** → Uses existing ELO formula from Discord bot
4. **Leaderboard Updates** → See your new rank at `/leaderboard`

### **Match History**

All confirmed matches appear in:
- Your match history (`/player/[your-discord-id]`)
- Global match feed (`/games`)
- Leaderboard statistics

### **Deck Tracking**

Deck URLs are stored with each match for:
- Meta analysis (most played decks)
- Deck performance stats
- Tournament deck lists

---

## 🎮 Pro Tips

1. **Play in Fullscreen** → Tap ⛶ for distraction-free gameplay
2. **Hand Phone to Opponent** → Top half of screen is rotated 180° for easy viewing
3. **Submit Reports Immediately** → Don't forget after the game ends!
4. **Add Deck URLs** → Helps track meta and deck performance
5. **Check Pending Confirmations** → Don't leave your opponents waiting!
6. **Use Recent Opponents** → They appear first in the search for quick selection

---

## 📞 Need Help?

- **Discord**: Ask in the #help channel on Sorcerers Summit Discord
- **Website**: [sorcererssummit.com](https://sorcererssummit.com)
- **Report Bugs**: Use `!report` in Discord or contact an admin

---

**Happy Gaming! 🎴✨**

*Last updated: March 2026*
