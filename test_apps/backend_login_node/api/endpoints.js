const userService = require('../services/user_service');
const ErrorCode = require('../controller/auth').ErrorCode;

exports.login = async (req, res) => {
    try {
        const { username, password } = req.body;
        const user = await userService.login(username, password);
        res.json({ 
            id: user.id, 
            username: user.username, 
            status: user.status, 
            created_at: user.created_at,
            error_code: ErrorCode.NO_ERROR,
            contract: "login",
            format: "json",
            status_code: 200
        });
    } catch (err) {
        res.status(err.status || 500).json({ 
            error_message: err.message, 
            error_code: ErrorCode.INVALID_REQUEST,
            created_at: new Date().toISOString(),
            contract: "login",
            format: "json",
            status_code: err.status || 500
        });
    }
};

exports.createUser = async (req, res) => {
    try {
        const { username, password } = req.body;
        const user = await userService.createUser(username, password);
        res.status(201).json({ 
            id: user.id, 
            username: user.username, 
            status: user.status, 
            created_at: user.created_at,
            error_code: ErrorCode.NO_ERROR,
            contract: "create-user",
            format: "json",
            status_code: 201
        });
    } catch (err) {
        res.status(err.status || 500).json({ 
            error_message: err.message, 
            error_code: ErrorCode.INVALID_REQUEST,
            created_at: new Date().toISOString(),
            contract: "create-user",
            format: "json",
            status_code: err.status || 500
        });
    }
};