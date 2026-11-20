import Link from 'next/link';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';

export default function ForgotPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4 py-12">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl font-bold">Password reset unavailable</CardTitle>
          <CardDescription>StockAI account recovery</CardDescription>
        </CardHeader>
        <CardContent>
          <Alert>
            <AlertDescription>
              Password reset is not configured in this deployment. No reset email has been sent.
              Contact the administrator for account recovery assistance.
            </AlertDescription>
          </Alert>
        </CardContent>
        <CardFooter className="justify-center">
          <Link href="/login" className="text-primary hover:underline font-medium">
            Return to sign in
          </Link>
        </CardFooter>
      </Card>
    </div>
  );
}
