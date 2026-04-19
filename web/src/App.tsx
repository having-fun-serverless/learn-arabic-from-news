import { Route, Switch } from 'wouter';
import Home from './routes/Home';
import Article from './routes/Article';

export default function App() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/article/:date/:slug" component={Article} />
      <Route>
        <div className="app-shell">
          <p className="error">לא נמצא דף.</p>
        </div>
      </Route>
    </Switch>
  );
}
