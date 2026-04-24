const auth = require('../controller/auth');
const userRepository = require('../repository/user_repository');

const authMiddleware = async (req, res, next) => {
    try {
        const { username, password } = req.body;
        const user = await auth(userRepository).authenticate({ username, password });
        req.user = user;
        next();
    } catch (err) {
        res.status(err.status || 500).json({ 
            error_message: err.message, 
            error_code: err.error_code, 
            created_at: new Date().toISOString() 
        });
    }
};

module.exports = authMiddleware;