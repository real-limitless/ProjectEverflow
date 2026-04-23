import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Fragment } from 'react';
import {
  LoginFooterItem,
  LoginForm,
  LoginMainFooterBandItem,
  LoginMainFooterLinksItem,
  LoginPage,
  ListItem,
  ListVariant,
  Button
} from '@patternfly/react-core';
import ExclamationCircleIcon from '@patternfly/react-icons/dist/esm/icons/exclamation-circle-icon';
import GoogleIcon from '@patternfly/react-icons/dist/esm/icons/google-icon';
import GithubIcon from '@patternfly/react-icons/dist/esm/icons/github-icon';
import DropboxIcon from '@patternfly/react-icons/dist/esm/icons/dropbox-icon';
import FacebookSquareIcon from '@patternfly/react-icons/dist/esm/icons/facebook-square-icon';
import GitlabIcon from '@patternfly/react-icons/dist/esm/icons/gitlab-icon';
import { login, isAuthenticated } from '@/lib/api';

const Login = () => {
  const navigate = useNavigate();
  const [showHelperText, setShowHelperText] = useState(false);
  const [username, setUsername] = useState('');
  const [isValidUsername, setIsValidUsername] = useState(true);
  const [password, setPassword] = useState('');
  const [isValidPassword, setIsValidPassword] = useState(true);
  const [isRememberMeChecked, setIsRememberMeChecked] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated()) {
      navigate('/');
    }
  }, [navigate]);

  const handleUsernameChange = (_event: React.FormEvent<HTMLInputElement>, value: string) => {
    setUsername(value);
  };

  const handlePasswordChange = (_event: React.FormEvent<HTMLInputElement>, value: string) => {
    setPassword(value);
  };

  const onRememberMeClick = () => {
    setIsRememberMeChecked(!isRememberMeChecked);
  };

  const onLoginButtonClick = async (event: React.MouseEvent<HTMLButtonElement, MouseEvent>) => {
    event.preventDefault();
    setIsLoading(true);

    // Basic validation
    const validUsername = !!username;
    const validPassword = !!password;
    setIsValidUsername(validUsername);
    setIsValidPassword(validPassword);

    if (!validUsername || !validPassword) {
      setShowHelperText(true);
      setIsLoading(false);
      return;
    }

    try {
      // Make API call to backend
      const result = await login(username, password);

      if (result.data) {
        // Store tokens
        localStorage.setItem('accessToken', result.data.access);
        localStorage.setItem('refreshToken', result.data.refresh);
        localStorage.setItem('isAuthenticated', 'true');

        // Store user info
        localStorage.setItem('username', username);

        // Navigate to dashboard
        navigate('/');
      } else {
        setShowHelperText(true);
        setIsValidUsername(false);
        setIsValidPassword(false);
      }
    } catch (err) {
      setShowHelperText(true);
      console.error('Login error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const socialMediaLoginContent = (
    <Fragment>
      <LoginMainFooterLinksItem>
        <Button variant="plain" aria-label="Login with Google" icon={<GoogleIcon />} />
      </LoginMainFooterLinksItem>
      <LoginMainFooterLinksItem>
        <Button variant="plain" aria-label="Login with Github" icon={<GithubIcon />} />
      </LoginMainFooterLinksItem>
      <LoginMainFooterLinksItem>
        <Button variant="plain" aria-label="Login with Dropbox" icon={<DropboxIcon />} />
      </LoginMainFooterLinksItem>
      <LoginMainFooterLinksItem>
        <Button variant="plain" aria-label="Login with Facebook" icon={<FacebookSquareIcon />} />
      </LoginMainFooterLinksItem>
      <LoginMainFooterLinksItem>
        <Button variant="plain" aria-label="Login with Gitlab" icon={<GitlabIcon />} />
      </LoginMainFooterLinksItem>
    </Fragment>
  );

  const signUpForAccountMessage = (
    <LoginMainFooterBandItem>
      Need an account? <a href="#contact">Contact your administrator.</a>
    </LoginMainFooterBandItem>
  );

  const forgotCredentials = (
    <LoginMainFooterBandItem>
      <a href="#reset">Forgot username or password?</a>
    </LoginMainFooterBandItem>
  );

  const listItem = (
    <Fragment>
      <ListItem>
        <LoginFooterItem href="#terms">Terms of Use</LoginFooterItem>
      </ListItem>
      <ListItem>
        <LoginFooterItem href="#help">Help</LoginFooterItem>
      </ListItem>
      <ListItem>
        <LoginFooterItem href="#privacy">Privacy Policy</LoginFooterItem>
      </ListItem>
    </Fragment>
  );

  const loginForm = (
    <LoginForm
      showHelperText={showHelperText}
      helperText="Invalid login credentials."
      helperTextIcon={<ExclamationCircleIcon />}
      usernameLabel="Username"
      usernameValue={username}
      onChangeUsername={handleUsernameChange}
      isValidUsername={isValidUsername}
      passwordLabel="Password"
      passwordValue={password}
      onChangePassword={handlePasswordChange}
      isValidPassword={isValidPassword}
      rememberMeLabel="Keep me logged in for 30 days."
      isRememberMeChecked={isRememberMeChecked}
      onChangeRememberMe={onRememberMeClick}
      onLoginButtonClick={onLoginButtonClick}
      loginButtonLabel={isLoading ? "Signing in..." : "Log in"}
      isLoginButtonDisabled={isLoading}
    />
  );

  return (
    <LoginPage
      footerListVariants={ListVariant.inline}
      brandImgSrc="https://github.com/patternfly/patternfly-react/raw/main/packages/react-core/src/components/assets/PF-IconLogo.svg"
      brandImgAlt="Everflow AI Platform logo"
      backgroundImgSrc="/assets/images/pf-background.svg"
      footerListItems={listItem}
      textContent="Welcome to Everflow AI Platform. This enterprise-grade collaborative AI application development platform enables teams to build, review, and deploy AI-powered applications with built-in safety, compliance, and approval workflows."
      loginTitle="Log in to your account"
      loginSubtitle="Enter your credentials to access the platform. Test credentials: developer / dev123"
      socialMediaLoginContent={socialMediaLoginContent}
      socialMediaLoginAriaLabel="Log in with social media"
      signUpForAccountMessage={signUpForAccountMessage}
      forgotCredentials={forgotCredentials}
    >
      {loginForm}
    </LoginPage>
  );
};

export default Login;