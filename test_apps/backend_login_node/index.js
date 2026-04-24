const express = require('express');
const app = express();
const userService = require('./services/user_service');
const authMiddleware = require('./middleware/auth');

app.use(express.json());

app.post('/login', async (req, res) => {
    try {
        const { username, password } = req.body;
        if (!username || !password) {
            res.status(400).json({ error_message: "username and password are required" });
            return;
        }
        const user = await userService.login(username, password);
        res.json({ 
            id: user.id, 
            username: user.username, 
            status: user.status, 
            created_at: user.created_at,
            error_code: user.error_code,
            contract: "login",
            format: "json",
            status_code: 200
        });
    } catch (err) {
        res.status(err.status || 500).json({ 
            error_message: err.message, 
            error_code: err.error_code, 
            created_at: new Date().toISOString(),
            contract: "login",
            format: "json",
            status_code: err.status || 500
        });
    }
});

app.post('/create-user', async (req, res) => {
    try {
        const { username, password } = req.body;
        if (!username || !password) {
            res.status(400).json({ error_message: "username and password are required" });
            return;
        }
        const user = await userService.createUser(username, password);
        res.status(201).json({ 
            id: user.id, 
            username: user.username, 
            status: user.status, 
            created_at: user.created_at,
            error_code: user.error_code,
            contract: "create-user",
            format: "json",
            status_code: 201
        });
    } catch (err) {
        res.status(err.status || 500).json({ 
            error_message: err.message, 
            error_code: err.error_code, 
            created_at: new Date().toISOString(),
            contract: "create-user",
            format: "json",
            status_code: err.status || 500
        });
    }
});

if (require.main === module) {
    app.listen(3000, () => console.log('started'));
}

module.exports = app;