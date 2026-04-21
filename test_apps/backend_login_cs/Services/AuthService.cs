namespace backend_login_cs.Services;
public interface IAuthService 
{
    bool Authenticate(string username, string password);
}

public class MockAuthService : IAuthService
{
    public bool Authenticate(string username, string password) 
    {
        // Improved implementation
        if (string.IsNullOrEmpty(username) || string.IsNullOrEmpty(password)) return false;

        if (username == "admin" && password == "secret123") 
        {
            return true;
        }
        return false;
    }
}